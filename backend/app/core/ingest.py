"""CSV ingestion.

Column names are auto-detected against a synonym table and returned to the UI
for confirmation with three sample rows, because silently guessing a mapping is
how a user ends up scoring the wrong column. Unmapped columns are retained as
passthrough so nothing the user brought is lost on export.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from . import normalize as nz
from .validate import validate_email

FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "company_name": ("company", "company name", "business name", "name", "organization",
                     "organisation", "account name", "legal name", "business"),
    "domain": ("domain", "website", "web site", "url", "company website", "site", "homepage"),
    "country": ("country", "country name", "nation"),
    "city": ("city", "town", "locality", "city name"),
    "industry": ("industry", "sector", "vertical", "category", "naics description", "sic description"),
    "employee_count": ("employees", "employee count", "headcount", "staff", "size",
                       "company size", "no of employees", "number of employees"),
    "revenue_estimate": ("revenue", "annual revenue", "revenue estimate", "turnover",
                         "estimated revenue", "sales"),
    "year_founded": ("founded", "year founded", "founded year", "established", "inception"),
    "owner_name": ("owner", "owner name", "contact", "contact name", "full name",
                   "first name", "principal", "ceo", "decision maker"),
    "contact_title": ("title", "job title", "position", "role", "contact title"),
    "email": ("email", "email address", "e-mail", "work email", "contact email"),
    "phone": ("phone", "phone number", "telephone", "mobile", "contact phone", "tel"),
    "linkedin_url": ("linkedin", "linkedin url", "linkedin profile", "linkedin company"),
}


@dataclass
class MappingReport:
    mapping: dict[str, str] = field(default_factory=dict)   # csv header -> canonical field
    unmapped: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    samples: list[dict] = field(default_factory=list)


def detect_mapping(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    normalized = {h: h.strip().lower().replace("_", " ") for h in headers}

    # exact synonym hits first, then substring, so "company website" doesn't
    # steal the slot that "company" should own.
    for canonical, synonyms in FIELD_SYNONYMS.items():
        for header, low in normalized.items():
            if header in mapping or canonical in taken:
                continue
            if low in synonyms:
                mapping[header] = canonical
                taken.add(canonical)
                break

    for canonical, synonyms in FIELD_SYNONYMS.items():
        if canonical in taken:
            continue
        for header, low in normalized.items():
            if header in mapping:
                continue
            if any(s in low for s in synonyms):
                mapping[header] = canonical
                taken.add(canonical)
                break

    return mapping


def preview(content: str, limit: int = 3) -> MappingReport:
    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []
    mapping = detect_mapping(headers)
    report = MappingReport(
        mapping=mapping,
        unmapped=[h for h in headers if h not in mapping],
        missing_required=[f for f in ("company_name",) if f not in mapping.values()],
    )
    for i, row in enumerate(reader):
        if i >= limit:
            break
        report.samples.append({mapping.get(k, k): v for k, v in row.items()})
    return report


def parse_rows(content: str, mapping: dict[str, str] | None = None,
               *, check_mx: bool = True) -> tuple[list[dict], MappingReport]:
    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []
    mapping = mapping or detect_mapping(headers)
    report = MappingReport(
        mapping=mapping,
        unmapped=[h for h in headers if h not in mapping],
        missing_required=[f for f in ("company_name",) if f not in mapping.values()],
    )

    rows: list[dict] = []
    for raw in reader:
        rec: dict = {"passthrough": {}, "provenance": {}, "merged_from": []}
        for header, value in raw.items():
            canonical = mapping.get(header)
            if canonical is None:
                if value not in (None, ""):
                    rec["passthrough"][header] = value
                continue
            rec[canonical] = value
            rec["provenance"][canonical] = {"source": "csv", "column": header}

        rec["company_name"] = (rec.get("company_name") or "").strip()
        if not rec["company_name"] and not rec.get("domain"):
            continue

        rec["normalized_name"] = nz.normalize_name(rec["company_name"])
        rec["domain"] = (rec.get("domain") or "").strip() or None
        rec["normalized_domain"] = nz.normalize_domain(rec.get("domain")) or nz.domain_from_email(rec.get("email"))
        if rec["normalized_domain"] and not rec["domain"]:
            rec["domain"] = rec["normalized_domain"]
            rec["provenance"]["domain"] = {"source": "derived", "column": "email"}

        rec["employee_count"] = nz.parse_int(rec.get("employee_count"))
        rec["revenue_estimate"] = nz.parse_revenue(rec.get("revenue_estimate"))
        rec["year_founded"] = nz.parse_int(rec.get("year_founded"))
        rec["phone"] = nz.normalize_phone(rec.get("phone"))
        rec["linkedin_url"] = nz.normalize_linkedin(rec.get("linkedin_url"))
        rec["industry"] = nz.normalize_industry(rec.get("industry"))

        email = (rec.get("email") or "").strip().lower() or None
        rec["email"] = email
        status, reason = validate_email(email, check_mx=check_mx)
        rec["email_status"] = status
        rec["email_reason"] = reason

        for key in ("country", "city", "owner_name", "contact_title"):
            val = rec.get(key)
            rec[key] = val.strip() if isinstance(val, str) and val.strip() else None

        rows.append(rec)

    return rows, report
