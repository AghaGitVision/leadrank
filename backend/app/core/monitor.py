"""Change detection.

A lead list decays. The value of holding one is knowing when something about a
company changes: a careers page appears, a site gets relaunched, "acquired by"
copy shows up. Diffing two scan snapshots of the same domain turns a static
export into a watchlist.

For a searcher, `pe_backed_appeared` means the target is gone. For a seller,
`careers_page_appeared` means budget just moved.
"""

from __future__ import annotations

from dataclasses import dataclass

WATCHED_FLAGS = ("has_careers", "has_blog", "has_cart")


@dataclass
class Change:
    kind: str
    detail: str
    severity: str  # info | opportunity | warning


def _year(payload: dict, key: str) -> int | None:
    v = payload.get(key)
    return int(v) if v else None


def diff_snapshots(old: dict, new: dict) -> list[Change]:
    changes: list[Change] = []

    old_status, new_status = old.get("status"), new.get("status")
    if old_status == "ok" and new_status != "ok":
        changes.append(Change("site_down", f"Site went from reachable to {new_status}.", "warning"))
    if old_status != "ok" and new_status == "ok":
        changes.append(Change("site_back", "Site is reachable again.", "info"))

    old_markers, new_markers = set(old.get("markers") or []), set(new.get("markers") or [])
    if "pe_backed" in new_markers - old_markers:
        changes.append(Change(
            "pe_backed_appeared",
            "Institutional-backing language appeared on the site. Likely no longer acquirable.",
            "warning"))
    if "recurring_revenue" in new_markers - old_markers:
        changes.append(Change(
            "recurring_revenue_appeared",
            "Contract or maintenance-plan language appeared.", "opportunity"))

    old_tech, new_tech = set(old.get("tech") or []), set(new.get("tech") or [])
    gained_tech = new_tech - old_tech
    if gained_tech & {"google_analytics", "hubspot", "meta_pixel"}:
        changes.append(Change(
            "analytics_added",
            f"Started running {', '.join(sorted(gained_tech & {'google_analytics', 'hubspot', 'meta_pixel'}))}.",
            "info"))
    if gained_tech & {"shopify", "webflow", "react"}:
        changes.append(Change(
            "site_relaunched",
            f"Moved onto {', '.join(sorted(gained_tech & {'shopify', 'webflow', 'react'}))}. "
            "Modernization upside just dropped.",
            "warning"))

    for flag in WATCHED_FLAGS:
        if new.get(flag) and not old.get(flag):
            label = {"has_careers": "careers page", "has_blog": "blog or news section",
                     "has_cart": "online store or checkout"}[flag]
            changes.append(Change(f"{flag}_appeared", f"A {label} appeared.", "opportunity"))
        if old.get(flag) and not new.get(flag):
            label = {"has_careers": "careers page", "has_blog": "blog or news section",
                     "has_cart": "online store or checkout"}[flag]
            changes.append(Change(f"{flag}_removed", f"The {label} was removed.", "info"))

    old_cy, new_cy = _year(old, "copyright_year"), _year(new, "copyright_year")
    if old_cy and new_cy and new_cy > old_cy:
        changes.append(Change("site_refreshed", f"Copyright year moved {old_cy} to {new_cy}.", "info"))

    return changes
