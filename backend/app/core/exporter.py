"""Export.

The reasoning has to survive the handoff. Score, band, confidence and the top
three contributions travel into the CRM as columns, so the rep who picks the
record up next week can see why it was queued without coming back here.
"""

from __future__ import annotations

import csv
import io

BASE_COLUMNS = [
    ("company_name", "Company"),
    ("domain", "Website"),
    ("industry", "Industry"),
    ("city", "City"),
    ("country", "Country"),
    ("employee_count", "Employees"),
    ("revenue_estimate", "Revenue estimate"),
    ("owner_name", "Contact"),
    ("email", "Email"),
    ("email_status", "Email status"),
    ("phone", "Phone"),
    ("linkedin_url", "LinkedIn"),
    ("score", "LeadRank score"),
    ("band", "Band"),
    ("confidence", "Confidence"),
    ("quadrant", "Action"),
    ("top_signals", "Why"),
    ("narrative", "Suggested angle"),
]

PRESETS = {
    "csv": {},
    "hubspot": {
        "company_name": "Name",
        "domain": "Company domain name",
        "industry": "Industry",
        "city": "City",
        "country": "Country/Region",
        "employee_count": "Number of Employees",
        "revenue_estimate": "Annual Revenue",
        "owner_name": "Contact owner",
        "email": "Email",
        "phone": "Phone Number",
        "linkedin_url": "LinkedIn Company Page",
        "score": "LeadRank Score",
        "band": "LeadRank Band",
        "confidence": "LeadRank Confidence",
        "quadrant": "LeadRank Action",
        "top_signals": "LeadRank Reasons",
        "narrative": "LeadRank Angle",
    },
    "salesforce": {
        "company_name": "Company",
        "domain": "Website",
        "industry": "Industry",
        "city": "City",
        "country": "Country",
        "employee_count": "NumberOfEmployees",
        "revenue_estimate": "AnnualRevenue",
        "owner_name": "LastName",
        "email": "Email",
        "phone": "Phone",
        "linkedin_url": "LinkedIn__c",
        "score": "LeadRank_Score__c",
        "band": "LeadRank_Band__c",
        "confidence": "LeadRank_Confidence__c",
        "quadrant": "LeadRank_Action__c",
        "top_signals": "LeadRank_Reasons__c",
        "narrative": "LeadRank_Angle__c",
    },
}

COMPLIANCE_NOTE = (
    "Exported by LeadRank. Business contact data gathered from public sources. "
    "Confirm a lawful basis (GDPR Art. 6(1)(f) legitimate interest or equivalent) "
    "and include a working opt-out in every message (CAN-SPAM s.5)."
)


def to_csv(rows: list[dict], preset: str = "csv", *, include_passthrough: bool = True,
           include_note: bool = True) -> str:
    mapping = PRESETS.get(preset, {})
    out = io.StringIO()

    passthrough_keys: list[str] = []
    if include_passthrough:
        seen: set[str] = set()
        for r in rows:
            for k in (r.get("passthrough") or {}):
                if not k.startswith("_") and k not in seen:
                    seen.add(k)
                    passthrough_keys.append(k)

    header = [mapping.get(key, label) for key, label in BASE_COLUMNS] + passthrough_keys
    writer = csv.writer(out)
    if include_note:
        writer.writerow([f"# {COMPLIANCE_NOTE}"])
    writer.writerow(header)

    for r in rows:
        line = []
        for key, _ in BASE_COLUMNS:
            v = r.get(key)
            if key == "confidence" and isinstance(v, (int, float)):
                v = f"{round(v * 100)}%"
            line.append("" if v is None else v)
        for k in passthrough_keys:
            line.append((r.get("passthrough") or {}).get(k, ""))
        writer.writerow(line)

    return out.getvalue()
