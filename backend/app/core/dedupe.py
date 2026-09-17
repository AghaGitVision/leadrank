"""Deduplication.

Two passes: exact on normalized domain, then fuzzy on normalized company name
within the same country. Merges keep the highest-confidence value per field and
record where each surviving value came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

AUTO_MERGE_THRESHOLD = 97
CANDIDATE_THRESHOLD = 92

# Higher = more trustworthy source for a given field during a merge.
SOURCE_RANK = {"scan": 3, "csv": 2, "derived": 1, "unknown": 0}

MERGEABLE_FIELDS = (
    "domain", "normalized_domain", "country", "city", "industry",
    "employee_count", "revenue_estimate", "year_founded", "owner_name",
    "email", "phone", "linkedin_url",
)


@dataclass
class DedupeReport:
    input_rows: int = 0
    exact_merges: int = 0
    fuzzy_merges: int = 0
    candidates: list[tuple[str, str, float]] = field(default_factory=list)

    @property
    def output_rows(self) -> int:
        return self.input_rows - self.exact_merges - self.fuzzy_merges


def _better(primary: dict, other: dict, field_name: str) -> bool:
    """Should `other`'s value for this field replace `primary`'s?"""
    pv, ov = primary.get(field_name), other.get(field_name)
    if ov in (None, ""):
        return False
    if pv in (None, ""):
        return True
    p_rank = SOURCE_RANK.get(primary.get("provenance", {}).get(field_name, {}).get("source", "unknown"), 0)
    o_rank = SOURCE_RANK.get(other.get("provenance", {}).get(field_name, {}).get("source", "unknown"), 0)
    if o_rank != p_rank:
        return o_rank > p_rank
    # tie-break on completeness: prefer the longer/greater value
    if isinstance(pv, str) and isinstance(ov, str):
        return len(ov) > len(pv)
    return False


def merge_rows(primary: dict, other: dict) -> dict:
    merged = dict(primary)
    merged.setdefault("provenance", {})
    for f in MERGEABLE_FIELDS:
        if _better(merged, other, f):
            merged[f] = other[f]
            src = other.get("provenance", {}).get(f, {"source": "csv"})
            merged["provenance"][f] = src
    merged["passthrough"] = {**other.get("passthrough", {}), **merged.get("passthrough", {})}
    merged["merged_from"] = list(merged.get("merged_from", [])) + [
        other.get("company_name", "")
    ] + list(other.get("merged_from", []))
    return merged


def dedupe(rows: list[dict]) -> tuple[list[dict], DedupeReport]:
    report = DedupeReport(input_rows=len(rows))

    # Pass 1 - exact normalized domain
    by_domain: dict[str, dict] = {}
    no_domain: list[dict] = []
    for row in rows:
        dom = row.get("normalized_domain")
        if not dom:
            no_domain.append(row)
            continue
        if dom in by_domain:
            by_domain[dom] = merge_rows(by_domain[dom], row)
            report.exact_merges += 1
        else:
            by_domain[dom] = row

    survivors = list(by_domain.values())

    # Pass 2 - fuzzy name within country, over rows that lack a domain plus the
    # domain survivors (a company can appear once with and once without a site).
    pool = survivors + no_domain
    kept: list[dict] = []
    for row in pool:
        name = row.get("normalized_name") or ""
        country = (row.get("country") or "").lower()
        match_idx, match_score = None, 0.0
        if name:
            for i, existing in enumerate(kept):
                if (existing.get("country") or "").lower() != country:
                    continue
                if existing.get("normalized_domain") and row.get("normalized_domain"):
                    continue  # different domains already proved they are distinct
                s = fuzz.token_sort_ratio(name, existing.get("normalized_name") or "")
                if s > match_score:
                    match_idx, match_score = i, s
        if match_idx is not None and match_score >= AUTO_MERGE_THRESHOLD:
            kept[match_idx] = merge_rows(kept[match_idx], row)
            report.fuzzy_merges += 1
        else:
            if match_idx is not None and match_score >= CANDIDATE_THRESHOLD:
                report.candidates.append(
                    (row.get("company_name", ""), kept[match_idx].get("company_name", ""), match_score)
                )
            kept.append(row)

    return kept, report
