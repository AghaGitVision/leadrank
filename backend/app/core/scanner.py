"""Signal scanner.

One polite HTTP pass per domain, not a crawl. At most three requests per host,
robots.txt honored, identifying user agent, bounded concurrency, per-host limit
of one. Everything extracted is parser or regex based — no model is involved in
producing a signal, because signals feed the score and the score must be
reproducible.

`scan_mode=offline` replays bundled fixtures so the demo and CI run without
egress. A fixture is marked `"fixture": true` in its payload and the UI labels
it, so nobody mistakes replayed data for a live fetch.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx
from selectolax.parser import HTMLParser

from ..config import get_settings
from .cache import scan_cache

FIXTURES_PATH = Path(__file__).resolve().parent.parent / "data" / "scan_fixtures.json"

OK = "ok"
UNREACHABLE = "unreachable"
TIMEOUT = "timeout"
BLOCKED = "blocked"
ROBOTS_DISALLOWED = "robots_disallowed"
NO_DOMAIN = "no_domain"

SECONDARY_PATHS = ("/about", "/contact", "/careers")

TECH_FINGERPRINTS = {
    "wordpress": r"wp-content|wp-includes|/wp-json",
    "shopify": r"cdn\.shopify\.com|shopify\.theme",
    "wix": r"static\.wixstatic\.com|wix\.com",
    "squarespace": r"squarespace\.com|static1\.squarespace",
    "webflow": r"webflow\.(com|io)|w-webflow",
    "hubspot": r"js\.hs-scripts\.com|hs-analytics",
    "google_analytics": r"gtag\(|google-analytics\.com|googletagmanager\.com",
    "meta_pixel": r"connect\.facebook\.net/.*fbevents",
    "calendly": r"calendly\.com",
    "stripe": r"js\.stripe\.com",
    "react": r"__NEXT_DATA__|react(-dom)?(\.production)?\.min\.js",
}

COPY_MARKERS = {
    "family_owned": r"family[- ]owned|family[- ]run|family business",
    "employee_owned": r"employee[- ]owned|esop\b",
    "pe_backed": r"a portfolio company of|backed by|acquired by|part of the [A-Z][a-z]+ group",
    "recurring_revenue": r"maintenance (plan|agreement|contract)|service (plan|agreement|contract)|subscription|retainer|annual contract",
    "multi_location": r"our locations|locations near|\b\d+ locations\b|branches",
    "booking": r"book (now|online|an appointment)|schedule (service|an appointment)|request a quote",
}

_SINCE = re.compile(r"(?:since|established|est\.?|serving .{0,30}since|founded(?: in)?)\s*(1[89]\d{2}|20[0-2]\d)", re.I)
_COPYRIGHT = re.compile(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", re.I)
_MAILTO = re.compile(r"mailto:([^\"'?\s>]+)", re.I)
_TEL = re.compile(r"tel:([+\d\-\s().]{7,})", re.I)

SOCIAL_HOSTS = {
    "linkedin": "linkedin.com",
    "facebook": "facebook.com",
    "instagram": "instagram.com",
    "twitter": "twitter.com",
    "x": "x.com",
    "youtube": "youtube.com",
}

CAREERS_HINTS = ("career", "jobs", "join-us", "join our team", "we're hiring", "we are hiring")
BLOG_HINTS = ("/blog", "/news", "/insights", "/resources")
CART_HINTS = ("/cart", "/checkout", "add to cart", "/shop", "/store")


def _empty_payload(status: str) -> dict:
    return {
        "status": status,
        "fixture": False,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "final_url": None,
        "https": False,
        "response_ms": None,
        "copyright_year": None,
        "since_year": None,
        "tech": [],
        "markers": [],
        "emails": [],
        "phones": [],
        "socials": [],
        "has_careers": False,
        "has_blog": False,
        "has_cart": False,
        "has_contact_form": False,
        "page_count_sampled": 0,
        "title": None,
        "meta_description": None,
        "text_length": 0,
    }


def parse_pages(pages: list[tuple[str, str]], *, final_url: str, https: bool, response_ms: int) -> dict:
    """Pure function: (url, html) pairs -> signal envelope. Unit-testable with no
    network, which is how the scoring tests stay deterministic."""
    payload = _empty_payload(OK)
    payload.update({"final_url": final_url, "https": https, "response_ms": response_ms,
                    "page_count_sampled": len(pages)})

    combined = "\n".join(html for _, html in pages)
    lowered = combined.lower()

    first_html = pages[0][1] if pages else ""
    tree = HTMLParser(first_html) if first_html else None
    if tree is not None:
        title_node = tree.css_first("title")
        payload["title"] = title_node.text(strip=True)[:200] if title_node else None
        desc = tree.css_first('meta[name="description"]')
        if desc is not None:
            payload["meta_description"] = (desc.attributes.get("content") or "")[:300]
        body = tree.body
        payload["text_length"] = len(body.text(separator=" ", strip=True)) if body is not None else 0

    years = [int(y) for y in _COPYRIGHT.findall(combined)]
    payload["copyright_year"] = max(years) if years else None
    since = [int(y) for y in _SINCE.findall(combined)]
    payload["since_year"] = min(since) if since else None

    payload["tech"] = sorted(k for k, pat in TECH_FINGERPRINTS.items() if re.search(pat, combined, re.I))
    payload["markers"] = sorted(k for k, pat in COPY_MARKERS.items() if re.search(pat, combined, re.I))

    payload["emails"] = sorted({e.lower() for e in _MAILTO.findall(combined)})[:5]
    payload["phones"] = sorted({p.strip() for p in _TEL.findall(combined)})[:5]

    socials = set()
    for name, host in SOCIAL_HOSTS.items():
        if host in lowered:
            socials.add("twitter" if name == "x" else name)
    payload["socials"] = sorted(socials)

    payload["has_careers"] = any(h in lowered for h in CAREERS_HINTS)
    payload["has_blog"] = any(h in lowered for h in BLOG_HINTS)
    payload["has_cart"] = any(h in lowered for h in CART_HINTS)
    payload["has_contact_form"] = "<form" in lowered and any(
        t in lowered for t in ("name=\"email\"", "type=\"email\"", "contact")
    )
    return payload


class Scanner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._sem = asyncio.Semaphore(self.settings.scan_concurrency)
        self._robots: dict[str, RobotFileParser | None] = {}
        self._fixtures: dict[str, dict] | None = None

    # ---------- offline ----------

    def _fixture_for(self, domain: str) -> dict | None:
        if self._fixtures is None:
            try:
                self._fixtures = json.loads(FIXTURES_PATH.read_text())
            except Exception:
                self._fixtures = {}
        fx = self._fixtures.get(domain)
        if fx is None:
            return None
        payload = _empty_payload(OK)
        payload.update(fx)
        payload["fixture"] = True
        payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
        return payload

    # ---------- live ----------

    async def _robots_allows(self, client: httpx.AsyncClient, domain: str, path: str) -> bool:
        if domain not in self._robots:
            rp: RobotFileParser | None = RobotFileParser()
            try:
                r = await client.get(f"https://{domain}/robots.txt", timeout=3.0)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                else:
                    rp = None
            except Exception:
                rp = None
            self._robots[domain] = rp
        rp = self._robots[domain]
        if rp is None:
            return True  # no robots.txt served == no restriction expressed
        return rp.can_fetch(self.settings.scan_user_agent, f"https://{domain}{path}")

    async def _fetch_live(self, domain: str) -> dict:
        headers = {"User-Agent": self.settings.scan_user_agent, "Accept": "text/html"}
        timeout = httpx.Timeout(self.settings.scan_timeout_seconds)
        started = asyncio.get_event_loop().time()
        async with self._sem:
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True, max_redirects=2, timeout=timeout, headers=headers
                ) as client:
                    if not await self._robots_allows(client, domain, "/"):
                        return _empty_payload(ROBOTS_DISALLOWED)
                    r = await client.get(f"https://{domain}/")
                    if r.status_code in (401, 403, 429):
                        return _empty_payload(BLOCKED)
                    if r.status_code >= 400:
                        return _empty_payload(UNREACHABLE)

                    pages = [(str(r.url), r.text)]
                    for path in self._pick_secondary(r.text, str(r.url)):
                        if not await self._robots_allows(client, domain, path):
                            continue
                        try:
                            sub = await client.get(urljoin(str(r.url), path))
                            if sub.status_code < 400:
                                pages.append((str(sub.url), sub.text))
                        except Exception:
                            continue
                        if len(pages) >= 3:
                            break

                    elapsed = int((asyncio.get_event_loop().time() - started) * 1000)
                    return parse_pages(
                        pages,
                        final_url=str(r.url),
                        https=str(r.url).startswith("https"),
                        response_ms=elapsed,
                    )
            except httpx.TimeoutException:
                return _empty_payload(TIMEOUT)
            except Exception:
                return _empty_payload(UNREACHABLE)

    @staticmethod
    def _pick_secondary(html: str, base: str) -> list[str]:
        lowered = html.lower()
        return [p for p in SECONDARY_PATHS if p in lowered][:2]

    # ---------- entry point ----------

    async def scan(self, domain: str | None) -> dict:
        if not domain:
            return _empty_payload(NO_DOMAIN)

        cached = scan_cache.get(domain)
        if cached is not None:
            cached["from_cache"] = True
            return cached

        if self.settings.scan_mode == "offline":
            payload = self._fixture_for(domain) or _empty_payload(UNREACHABLE)
        else:
            payload = await self._fetch_live(domain)

        payload["from_cache"] = False
        scan_cache.put(domain, payload)
        return payload

    async def scan_many(self, domains: list[str | None]) -> list[dict]:
        return await asyncio.gather(*(self.scan(d) for d in domains))


scanner = Scanner()
