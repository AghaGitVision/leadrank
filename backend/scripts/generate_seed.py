"""Generates the bundled demo dataset.

Two files are produced:
  app/data/seed_leads.csv     — a messy lead list, as exported from a scraper
  app/data/scan_fixtures.json — the signal envelopes the offline scanner replays

The generator is seeded, so the dataset is reproducible and the scoring tests
can assert on exact numbers. The messiness is deliberate: mixed revenue
formats, duplicate rows with different spellings, missing columns, junk
whitespace, role-account emails. A clean demo dataset proves nothing.

Run: python scripts/generate_seed.py
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

random.seed(20260915)

OUT = Path(__file__).resolve().parent.parent / "app" / "data"
OUT.mkdir(parents=True, exist_ok=True)

INDUSTRIES = [
    ("HVAC", "hvac"), ("Plumbing", "plumbing"), ("Electrical Contracting", "electrical"),
    ("Roofing", "roofing"), ("Landscaping", "landscaping"), ("Pest Control", "pest control"),
    ("Dental Practice", "dental"), ("Veterinary Services", "veterinary"),
    ("Precision Machining", "machining"), ("Metal Fabrication", "fabrication"),
    ("Commercial Janitorial", "janitorial"), ("Waste Management", "waste"),
    ("Staffing & Recruiting", "staffing"), ("Third Party Logistics", "logistics"),
    ("Accounting Services", "accounting"), ("Auto Repair", "auto repair"),
    ("Digital Marketing Agency", "marketing"), ("Software Consulting", "software"),
    ("Real Estate Brokerage", "real estate"), ("Event Planning", "events"),
]

CITIES = [
    ("Austin", "TX"), ("Dallas", "TX"), ("Houston", "TX"), ("Phoenix", "AZ"),
    ("Tucson", "AZ"), ("Denver", "CO"), ("Columbus", "OH"), ("Cleveland", "OH"),
    ("Charlotte", "NC"), ("Raleigh", "NC"), ("Nashville", "TN"), ("Tampa", "FL"),
    ("Orlando", "FL"), ("Kansas City", "MO"), ("Indianapolis", "IN"),
    ("Milwaukee", "WI"), ("Portland", "OR"), ("Sacramento", "CA"),
    ("Toronto", "ON"), ("Manchester", "UK"),
]

FIRST = ["Maria", "James", "Robert", "Linda", "David", "Susan", "Frank", "Carol",
         "Miguel", "Anne", "Thomas", "Patricia", "Kevin", "Donna", "Raymond",
         "Gloria", "Walter", "Nancy", "Hector", "Ruth", "Dennis", "Sharon"]
LAST = ["Delgado", "Whitfield", "Okonkwo", "Barrett", "Nakamura", "Castellanos",
        "Pruitt", "Halloran", "Vasquez", "Lindqvist", "Ferraro", "Muldoon",
        "Ashworth", "Bhatti", "Renner", "Coyle", "Stanek", "Ivers", "Marchetti",
        "Toussaint", "Kellerman", "Ngo"]
SUFFIX = ["Services", "Systems", "Group", "Solutions", "Company", "& Sons",
          "Contractors", "Partners", "Industries", "Works"]
TITLES = ["Owner", "President", "Founder", "General Manager", "Operations Manager",
          "Managing Director", "VP Operations", "Office Manager", ""]

LEGAL = ["", " LLC", " Inc.", " Inc", " Ltd", " Co."]


def slug(name: str) -> str:
    keep = "".join(c for c in name.lower() if c.isalnum() or c == " ")
    parts = keep.split()
    return "".join(parts[:2])[:22] or "company"


def revenue_text(value: float) -> str:
    """Same number, five different spellings. The parser has to cope."""
    style = random.randint(0, 4)
    if style == 0:
        return str(int(value))
    if style == 1:
        return f"${value/1_000_000:.1f}M"
    if style == 2:
        return f"{value/1_000_000:.2f} million"
    if style == 3:
        return f"{int(value):,}"
    return f"${int(value):,}"


def employee_text(value: int) -> str:
    style = random.randint(0, 2)
    if style == 0:
        return str(value)
    if style == 1:
        return f"{max(1, value - 5)}-{value + 5}"
    return f"{value} employees"


def make_company(i: int) -> dict:
    industry_label, industry_key = random.choice(INDUSTRIES)
    city, state = random.choice(CITIES)
    country = {"ON": "Canada", "UK": "United Kingdom"}.get(state, "United States")

    surname = random.choice(LAST)
    pattern = random.randint(0, 3)
    if pattern == 0:
        base = f"{surname} {industry_label.split()[0]}"
    elif pattern == 1:
        base = f"{city} {industry_label.split()[0]} {random.choice(SUFFIX)}"
    elif pattern == 2:
        base = f"{surname} & {random.choice(LAST)}"
    else:
        base = f"{random.choice(['Summit', 'Ironwood', 'Blue Ridge', 'Cardinal', 'Riverside', 'Granite', 'Silverline', 'Harbor'])} {industry_label.split()[0]}"
    name = base + random.choice(LEGAL)

    domain = f"{slug(base)}.com"
    employees = random.choice([4, 8, 12, 18, 22, 26, 31, 38, 45, 60, 85, 120, 190, 340])
    revenue = employees * random.randint(90_000, 240_000)
    founded = random.choice([1972, 1984, 1991, 1996, 2001, 2004, 2009, 2013, 2017, 2021])

    owner_first = random.choice(FIRST)
    owner_last = surname if pattern in (0, 2) and random.random() < 0.7 else random.choice(LAST)
    title = random.choice(TITLES)

    email_style = random.random()
    if email_style < 0.30:
        email = f"info@{domain}"
    elif email_style < 0.60:
        email = f"{owner_first[0].lower()}{owner_last.lower()}@{domain}"
    elif email_style < 0.72:
        email = f"{owner_first.lower()}.{owner_last.lower()}@gmail.com"
    elif email_style < 0.80:
        email = ""
    elif email_style < 0.85:
        email = f"contact@{slug(base)}"  # malformed on purpose
    else:
        email = f"{owner_first.lower()}@{domain}"

    phone_style = random.random()
    if phone_style < 0.2:
        phone = ""
    elif phone_style < 0.6:
        phone = f"({random.randint(200,989)}) {random.randint(200,999)}-{random.randint(1000,9999)}"
    else:
        phone = f"+1{random.randint(2000000000, 9899999999)}"

    return {
        "row": {
            "Company Name": name,
            "Website": random.choice(["https://www.", "http://", "www.", ""]) + domain,
            "Industry": industry_label,
            "City": city,
            "Country": country,
            "Employees": employee_text(employees) if random.random() > 0.08 else "",
            "Annual Revenue": revenue_text(revenue) if random.random() > 0.15 else "",
            "Year Founded": str(founded) if random.random() > 0.25 else "",
            "Owner": f"{owner_first} {owner_last}" if random.random() > 0.18 else "",
            "Title": title,
            "Email": email,
            "Phone": phone,
            "LinkedIn": f"linkedin.com/company/{slug(base)}" if random.random() > 0.55 else "",
            "Source List": random.choice(["directory_q3", "trade_assoc", "chamber_export"]),
        },
        "meta": {
            "domain": domain, "industry_key": industry_key, "employees": employees,
            "founded": founded, "name": name,
        },
    }


def make_fixture(meta: dict) -> dict:
    """Signal envelope. Correlated with the firmographics so the dataset tells a
    coherent story: older, smaller, trade-industry companies tend to have
    neglected sites, which is exactly the buy-mode thesis."""
    founded, employees = meta["founded"], meta["employees"]
    old_school = founded < 2005 and employees < 90

    status_roll = random.random()
    if status_roll < 0.06:
        return {"status": "unreachable"}
    if status_roll < 0.09:
        return {"status": "timeout"}
    if status_roll < 0.11:
        return {"status": "blocked"}

    tech: list[str] = []
    markers: list[str] = []
    socials: list[str] = []

    modern = (not old_school) or random.random() < 0.25
    if modern:
        tech += random.sample(["react", "webflow", "hubspot", "shopify"], k=random.randint(1, 2))
        tech.append("google_analytics")
        socials += random.sample(["linkedin", "facebook", "instagram", "youtube"], k=random.randint(2, 4))
        copyright_year = random.choice([2025, 2026, 2026, 2024])
    else:
        if random.random() < 0.7:
            tech.append("wordpress")
        if random.random() < 0.25:
            tech.append("google_analytics")
        socials += random.sample(["facebook", "linkedin"], k=random.randint(0, 2))
        copyright_year = random.choice([2016, 2018, 2019, 2020, 2021, 2022])

    if old_school and random.random() < 0.45:
        markers.append("family_owned")
    if random.random() < 0.30:
        markers.append("recurring_revenue")
    if random.random() < 0.15:
        markers.append("multi_location")
    if random.random() < 0.07:
        markers.append("pe_backed")
    if modern and random.random() < 0.4:
        markers.append("booking")

    return {
        "status": "ok",
        "https": random.random() > (0.30 if old_school else 0.03),
        "response_ms": random.randint(120, 2600),
        "copyright_year": copyright_year,
        "since_year": founded if random.random() < 0.55 else None,
        "tech": sorted(set(tech)),
        "markers": sorted(set(markers)),
        "emails": [],
        "phones": [f"+1{random.randint(2000000000, 9899999999)}"] if random.random() < 0.6 else [],
        "socials": sorted(set(socials)),
        "has_careers": random.random() < (0.45 if modern else 0.12),
        "has_blog": random.random() < (0.55 if modern else 0.10),
        "has_cart": random.random() < (0.30 if modern else 0.04),
        "has_contact_form": random.random() < 0.8,
        "page_count_sampled": random.randint(1, 3),
        "title": f"{meta['name']} | {meta['industry_key'].title()}",
        "meta_description": None,
        "text_length": random.randint(600, 9000),
    }


def main() -> None:
    companies = [make_company(i) for i in range(300)]

    # Duplicates: same company, different spelling and partial data. This is
    # what the dedupe pass exists for, and it has to be in the demo data.
    dupes = []
    for c in random.sample(companies, 22):
        row = dict(c["row"])
        name = row["Company Name"]
        variant = name.replace(" LLC", "").replace(" Inc.", "").replace(" Inc", "").strip()
        if random.random() < 0.5:
            variant = variant.upper()
        row["Company Name"] = variant
        if random.random() < 0.5:
            row["Website"] = ""
        row["Email"] = ""
        row["Employees"] = ""
        row["Source List"] = "chamber_export"
        dupes.append({"row": row, "meta": c["meta"]})

    all_rows = companies + dupes
    random.shuffle(all_rows)

    headers = list(all_rows[0]["row"].keys())
    with (OUT / "seed_leads.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for item in all_rows:
            writer.writerow(item["row"])

    fixtures = {c["meta"]["domain"]: make_fixture(c["meta"]) for c in companies}
    (OUT / "scan_fixtures.json").write_text(json.dumps(fixtures, indent=1, sort_keys=True))

    print(f"wrote {len(all_rows)} rows ({len(dupes)} deliberate duplicates)")
    print(f"wrote {len(fixtures)} scan fixtures")


if __name__ == "__main__":
    main()
