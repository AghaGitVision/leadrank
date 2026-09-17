"""Flattens a lead record plus its scan envelope into the feature bag the
scoring engine reads. Keeping this separate means scoring never touches a
database row or an HTTP response, which is what makes it trivially testable."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import scanner as scanner_mod
from .validate import email_quality

SENIORITY_TIERS = {
    1.0: ("owner", "founder", "co-founder", "president", "ceo", "chief executive",
          "proprietor", "managing director", "partner", "principal"),
    0.7: ("cto", "cfo", "coo", "cmo", "chief", "vp", "vice president", "director", "head of"),
    0.4: ("manager", "lead", "supervisor", "general manager"),
}


@dataclass
class Features:
    company_name: str = ""
    normalized_name: str = ""
    domain: str | None = None
    country: str | None = None
    city: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    revenue_estimate: float | None = None
    year_founded: int | None = None

    owner_name: str | None = None
    contact_title: str | None = None
    email: str | None = None
    email_status: str = "unknown"
    phone: str | None = None
    linkedin_url: str | None = None

    scan_status: str = "not_scanned"
    scan: dict = field(default_factory=dict)

    # --- derived conveniences -------------------------------------------------

    @property
    def site_ok(self) -> bool:
        return self.scan.get("status") == scanner_mod.OK

    @property
    def tech(self) -> set[str]:
        return set(self.scan.get("tech") or [])

    @property
    def markers(self) -> set[str]:
        return set(self.scan.get("markers") or [])

    @property
    def socials(self) -> set[str]:
        return set(self.scan.get("socials") or [])

    @property
    def effective_founded(self) -> int | None:
        if self.year_founded:
            return self.year_founded
        return self.scan.get("since_year")

    @property
    def years_in_business(self) -> int | None:
        founded = self.effective_founded
        if not founded:
            return None
        return max(0, datetime.now(timezone.utc).year - founded)

    @property
    def site_age_gap(self) -> int | None:
        """Years since the site's copyright year. High = neglected."""
        cy = self.scan.get("copyright_year")
        if not cy:
            return None
        return max(0, datetime.now(timezone.utc).year - int(cy))

    @property
    def email_score(self) -> float | None:
        if not self.email:
            return None
        return email_quality(self.email_status)

    @property
    def seniority(self) -> float | None:
        text = " ".join(filter(None, [self.contact_title, self.owner_name])).lower()
        if not text.strip():
            return None
        for value, needles in SENIORITY_TIERS.items():
            if any(n in text for n in needles):
                return value
        return 0.25

    @property
    def owner_matches_company(self) -> bool:
        """`Delgado HVAC` + owner `Maria Delgado` -> owner-operated signal."""
        if not self.owner_name or not self.normalized_name:
            return False
        surname = self.owner_name.strip().split()[-1].lower()
        return len(surname) > 2 and surname in self.normalized_name


def build_features(lead: dict, scan: dict | None = None) -> Features:
    scan = scan or {}
    return Features(
        company_name=lead.get("company_name") or "",
        normalized_name=lead.get("normalized_name") or "",
        domain=lead.get("normalized_domain") or lead.get("domain"),
        country=lead.get("country"),
        city=lead.get("city"),
        industry=lead.get("industry"),
        employee_count=lead.get("employee_count"),
        revenue_estimate=lead.get("revenue_estimate"),
        year_founded=lead.get("year_founded"),
        owner_name=lead.get("owner_name"),
        contact_title=lead.get("contact_title") or (lead.get("passthrough") or {}).get("title"),
        email=lead.get("email"),
        email_status=lead.get("email_status") or "unknown",
        phone=lead.get("phone"),
        linkedin_url=lead.get("linkedin_url"),
        scan_status=scan.get("status", lead.get("scan_status", "not_scanned")),
        scan=scan,
    )
