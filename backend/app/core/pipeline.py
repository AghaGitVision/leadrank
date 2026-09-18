"""Run orchestration: ingest -> dedupe -> suppress -> scan -> score -> persist.

Scoring is separated from scanning on purpose. Rescoring replays cached signals
through new weights without touching the network, which is what makes live
weight-tuning possible and keeps the demo honest.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Alert, Lead, LeadSignal, Run, ScanSnapshot, ScoringProfile, SuppressionEntry
from .cache import scan_cache
from .dedupe import dedupe
from .features import build_features
from .monitor import diff_snapshots
from .narrative import deterministic_summary, llm_summary
from .scanner import scanner
from .scoring import score_lead
from .sources import LeadSource

PROGRESS_INGEST = 0.15
PROGRESS_SCAN_END = 0.80


def _lead_to_dict(lead: Lead) -> dict:
    return {
        "company_name": lead.company_name,
        "normalized_name": lead.normalized_name,
        "domain": lead.domain,
        "normalized_domain": lead.normalized_domain,
        "country": lead.country,
        "city": lead.city,
        "industry": lead.industry,
        "employee_count": lead.employee_count,
        "revenue_estimate": lead.revenue_estimate,
        "year_founded": lead.year_founded,
        "owner_name": lead.owner_name,
        "email": lead.email,
        "email_status": lead.email_status,
        "phone": lead.phone,
        "linkedin_url": lead.linkedin_url,
        "passthrough": lead.passthrough or {},
        "scan_status": lead.scan_status,
    }


def apply_score(db: Session, lead: Lead, profile: ScoringProfile, *, narrative: str | None = None) -> None:
    features = build_features(_lead_to_dict(lead), lead.scan_payload or {})
    result = score_lead(
        features,
        mode=profile.mode,
        weights=profile.weights or {},
        targeting=profile.targeting or {},
    )

    lead.score = result.score
    lead.band = result.band
    lead.confidence = result.confidence
    lead.quadrant = result.quadrant
    lead.narrative = narrative or deterministic_summary(features, result, profile.mode)

    db.query(LeadSignal).filter(LeadSignal.lead_id == lead.id).delete(synchronize_session=False)
    for c in result.contributions:
        db.add(LeadSignal(
            lead_id=lead.id,
            dimension=c.dimension,
            signal_key=c.signal_key,
            label=c.label,
            raw_value=None if c.normalized is None else str(c.normalized),
            normalized_value=c.normalized,
            weight=c.weight,
            contribution=c.contribution,
            forgone=c.forgone,
            present=c.present,
            source="scan" if c.dimension in ("digital_maturity", "growth_signals",
                                             "modernization_upside") else "csv",
        ))
    lead.passthrough = {**(lead.passthrough or {}),
                        "_dimension_scores": result.dimension_scores}


async def execute_run(db: Session, run: Run, source: LeadSource, **fetch_params) -> None:
    """Runs any `LeadSource` (a CSV upload, a SaaSquatch search, or a future
    adapter) through the same dedupe -> suppress -> scan -> score pipeline.
    Scoring never learns where a row came from."""
    profile = db.get(ScoringProfile, run.profile_id)
    assert profile is not None

    run.status = "ingesting"
    db.commit()

    rows = await source.fetch(**fetch_params)
    unmapped_columns = getattr(source, "last_unmapped_columns", [])
    rows, dd_report = dedupe(rows)

    suppressed_domains = {s.domain for s in db.scalars(select(SuppressionEntry)).all()}
    before = len(rows)
    rows = [r for r in rows if r.get("normalized_domain") not in suppressed_domains]
    suppressed = before - len(rows)

    run.row_count = len(rows)
    run.progress = PROGRESS_INGEST
    run.status = "scanning"
    db.commit()

    leads: list[Lead] = []
    for r in rows:
        lead = Lead(
            run_id=run.id,
            company_name=r.get("company_name") or r.get("domain") or "Unknown",
            normalized_name=r.get("normalized_name") or "",
            domain=r.get("domain"),
            normalized_domain=r.get("normalized_domain"),
            country=r.get("country"),
            city=r.get("city"),
            industry=r.get("industry"),
            employee_count=r.get("employee_count"),
            revenue_estimate=r.get("revenue_estimate"),
            year_founded=r.get("year_founded"),
            owner_name=r.get("owner_name"),
            email=r.get("email"),
            email_status=r.get("email_status", "unknown"),
            phone=r.get("phone"),
            linkedin_url=r.get("linkedin_url"),
            passthrough={**r.get("passthrough", {}),
                         **({"title": r["contact_title"]} if r.get("contact_title") else {}),
                         **({"_email_reason": r["email_reason"]} if r.get("email_reason") else {})},
            provenance=r.get("provenance", {}),
            merged_from=r.get("merged_from", []),
        )
        db.add(lead)
        leads.append(lead)
    db.commit()

    # --- scan -------------------------------------------------------------
    total = max(1, len(leads))
    done = 0
    alerts_created = 0
    batch = 16
    for i in range(0, len(leads), batch):
        chunk = leads[i : i + batch]
        payloads = await scanner.scan_many([lead.normalized_domain for lead in chunk])
        for lead, payload in zip(chunk, payloads):
            lead.scan_payload = payload
            lead.scan_status = payload.get("status", "not_scanned")
            if lead.normalized_domain:
                previous = db.scalars(
                    select(ScanSnapshot)
                    .where(ScanSnapshot.domain == lead.normalized_domain)
                    .order_by(ScanSnapshot.fetched_at.desc())
                ).first()
                if previous is not None:
                    for change in diff_snapshots(previous.payload or {}, payload):
                        db.add(Alert(domain=lead.normalized_domain, lead_id=lead.id,
                                     kind=change.kind, detail=change.detail,
                                     severity=change.severity))
                        alerts_created += 1
                db.add(ScanSnapshot(domain=lead.normalized_domain,
                                    status=payload.get("status", "unknown"),
                                    payload=payload))
        done += len(chunk)
        run.progress = PROGRESS_INGEST + (PROGRESS_SCAN_END - PROGRESS_INGEST) * (done / total)
        db.commit()
        await asyncio.sleep(0)

    # --- score ------------------------------------------------------------
    run.status = "scoring"
    db.commit()
    for lead in leads:
        apply_score(db, lead, profile)
    db.commit()

    bands: dict[str, int] = {}
    quadrants: dict[str, int] = {}
    scan_statuses: dict[str, int] = {}
    for lead in leads:
        bands[lead.band] = bands.get(lead.band, 0) + 1
        quadrants[lead.quadrant] = quadrants.get(lead.quadrant, 0) + 1
        scan_statuses[lead.scan_status] = scan_statuses.get(lead.scan_status, 0) + 1

    run.stats = {
        "input_rows": dd_report.input_rows,
        "exact_merges": dd_report.exact_merges,
        "fuzzy_merges": dd_report.fuzzy_merges,
        "merge_candidates": len(dd_report.candidates),
        "suppressed": suppressed,
        "unmapped_columns": unmapped_columns,
        "source": source.name,
        "bands": bands,
        "quadrants": quadrants,
        "scan_statuses": scan_statuses,
        "scan_cache_hit_rate": scan_cache.hit_rate,
        "cache_backend": scan_cache.kind,
        "alerts": alerts_created,
    }
    run.progress = 1.0
    run.status = "complete"
    run.completed_at = datetime.now(timezone.utc)
    db.commit()


async def attach_narratives(db: Session, run: Run, limit: int = 25) -> int:
    """Optional pass: rewrite the top N summaries with the model. Never changes
    a score; runs after the run is already usable."""
    profile = db.get(ScoringProfile, run.profile_id)
    leads = db.scalars(
        select(Lead).where(Lead.run_id == run.id).order_by(Lead.score.desc()).limit(limit)
    ).all()
    written = 0
    for lead in leads:
        features = build_features(_lead_to_dict(lead), lead.scan_payload or {})
        result = score_lead(features, mode=profile.mode, weights=profile.weights or {},
                            targeting=profile.targeting or {})
        text, generated = await llm_summary(features, result, profile.mode)
        if generated:
            lead.narrative = text
            written += 1
    db.commit()
    return written
