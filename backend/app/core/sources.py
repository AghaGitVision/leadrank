"""Lead source adapters.

CSV is the v1 path because it works today against SaaSquatch's existing export.
The point of this module is that scoring never learns where a lead came from:
`execute_run` (see `pipeline.py`) takes any `LeadSource`, so both adapters run
through the identical dedupe -> scan -> score pipeline.

`SaaSquatchSource` is wired through `POST /api/v1/runs/search`
(`app/api/runs.py`) — it stays inert without `LEADRANK_SAASQUATCH_API_KEY` set,
in which case that endpoint returns 400 rather than silently no-op'ing.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from .ingest import parse_rows


class LeadSource(Protocol):
    name: str

    async def fetch(self, **params) -> list[dict]:
        ...


class CsvSource:
    name = "csv"

    def __init__(self, content: str, mapping: dict | None = None, check_mx: bool = False):
        self.content = content
        self.mapping = mapping
        self.check_mx = check_mx
        self.last_unmapped_columns: list[str] = []

    async def fetch(self, **params) -> list[dict]:
        rows, report = parse_rows(self.content, self.mapping, check_mx=self.check_mx)
        self.last_unmapped_columns = report.unmapped
        return rows


class SaaSquatchSource:
    """Scores at search time instead of post-export.

    The host product already knows industry, location, headcount and revenue
    estimate before a credit is spent. Ranking that result set is strictly more
    useful than ranking a CSV after the fact, because the ranking can then drive
    which rows are worth enriching.
    """

    name = "saasquatch"

    def __init__(self, api_key: str, base_url: str = "https://api.saasquatchleads.com/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def fetch(self, *, industry: str | None = None, country: str | None = None,
                    min_employees: int | None = None, max_employees: int | None = None,
                    limit: int = 100, **_) -> list[dict]:
        if not self.api_key:
            raise RuntimeError("SaaSquatch source requires an API key")
        params = {k: v for k, v in {
            "industry": industry, "country": country,
            "min_employees": min_employees, "max_employees": max_employees,
            "limit": limit,
        }.items() if v is not None}
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                f"{self.base_url}/companies",
                params=params,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            r.raise_for_status()
            return [self._map(item) for item in r.json().get("data", [])]

    @staticmethod
    def _map(item: dict) -> dict:
        from . import normalize as nz

        name = item.get("company_name") or item.get("name") or ""
        return {
            "company_name": name,
            "normalized_name": nz.normalize_name(name),
            "domain": item.get("website"),
            "normalized_domain": nz.normalize_domain(item.get("website")),
            "country": item.get("country"),
            "city": item.get("city"),
            "industry": nz.normalize_industry(item.get("industry")),
            "employee_count": nz.parse_int(item.get("employee_count")),
            "revenue_estimate": nz.parse_revenue(item.get("revenue_estimate")),
            "owner_name": item.get("owner_name"),
            "email": (item.get("email") or "").lower() or None,
            "phone": nz.normalize_phone(item.get("phone")),
            "linkedin_url": nz.normalize_linkedin(item.get("linkedin_url")),
            "passthrough": {},
            "provenance": {k: {"source": "saasquatch"} for k in
                           ("domain", "industry", "employee_count", "revenue_estimate")},
            "merged_from": [],
            "email_status": "unknown",
        }
