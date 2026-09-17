"""Field normalization. Runs before dedupe and scoring so that every downstream
comparison is made on a canonical form."""

from __future__ import annotations

import re

LEGAL_SUFFIXES = {
    "llc", "l.l.c", "inc", "inc.", "incorporated", "ltd", "ltd.", "limited",
    "corp", "corp.", "corporation", "co", "co.", "company", "gmbh", "bv", "nv",
    "plc", "pty", "llp", "lp", "pc", "sa", "srl", "ag", "oy", "ab", "as",
}

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_DIGITS = re.compile(r"\d+")

# Order matters: longest multiplier suffix first.
_REVENUE_UNITS = [("b", 1_000_000_000), ("m", 1_000_000), ("k", 1_000)]


def normalize_domain(value: str | None) -> str | None:
    """`HTTPS://WWW.Example.com/path?x=1` -> `example.com`."""
    if not value:
        return None
    v = value.strip().lower()
    v = re.sub(r"^[a-z]+://", "", v)
    v = v.split("/")[0].split("?")[0].split("#")[0]
    v = v.removeprefix("www.")
    v = v.split(":")[0]
    if "." not in v or " " in v:
        return None
    return v or None


def domain_from_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return normalize_domain(email.rsplit("@", 1)[1])


def normalize_name(value: str | None) -> str:
    """Casefold, drop punctuation and legal suffixes. Used only for matching;
    the display name is always preserved untouched."""
    if not value:
        return ""
    v = _NON_ALNUM.sub(" ", value.strip().lower())
    tokens = [t for t in _WS.split(v) if t and t not in LEGAL_SUFFIXES]
    return " ".join(tokens)


def normalize_phone(value: str | None, default_country_code: str = "1") -> str | None:
    """Best-effort E.164. Deliberately not a full libphonenumber dependency —
    the signal we need is 'is there a reachable direct line', not perfect parsing."""
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit() or ch == "+")
    if digits.startswith("+"):
        rest = "".join(ch for ch in digits[1:] if ch.isdigit())
        return f"+{rest}" if 8 <= len(rest) <= 15 else None
    digits = "".join(ch for ch in digits if ch.isdigit())
    if len(digits) == 10:
        return f"+{default_country_code}{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}" if 8 <= len(digits) <= 15 else None


def parse_int(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    m = _DIGITS.findall(str(value).replace(",", ""))
    if not m:
        return None
    nums = [int(x) for x in m]
    # "10-50 employees" -> midpoint, which is what a band check wants
    return sum(nums[:2]) // 2 if len(nums) >= 2 and "-" in str(value) else nums[0]


def parse_revenue(value) -> float | None:
    """Accepts 2500000, '$2.5M', '2.5 million', '1.2B'."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower().replace(",", "").replace("$", "").replace("usd", "")
    s = s.replace("million", "m").replace("billion", "b").replace("thousand", "k")
    s = s.strip()
    mult = 1.0
    for suffix, factor in _REVENUE_UNITS:
        if s.endswith(suffix):
            mult = factor
            s = s[: -len(suffix)].strip()
            break
    try:
        return float(s) * mult
    except ValueError:
        return None


def normalize_linkedin(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if not v:
        return None
    if not v.startswith("http"):
        v = "https://" + v.lstrip("/")
    return v if "linkedin.com" in v.lower() else None


def normalize_industry(value: str | None) -> str | None:
    if not value:
        return None
    return _WS.sub(" ", value.strip().lower()) or None
