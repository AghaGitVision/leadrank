from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.learning import learn_weights
from ..core.monitor import diff_snapshots
from ..core.scanner import scanner
from ..db import get_db
from ..models import Alert, Decision, Lead, Run, ScanSnapshot, ScoringProfile, SuppressionEntry
from ..schemas import AlertOut, LearningOut

router = APIRouter(prefix="/api/v1", tags=["insights"])


@router.get("/runs/{run_id}/learning", response_model=LearningOut)
def learning(run_id: str, db: Session = Depends(get_db)):
    """Proposes new weights from this run's accept/reject decisions. Proposes
    only — the active profile is never mutated here."""
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    profile = db.get(ScoringProfile, run.profile_id)

    decisions = db.scalars(select(Decision).where(Decision.run_id == run_id)).all()
    result = learn_weights(
        [(d.state, d.dimension_scores or {}) for d in decisions],
        mode=profile.mode,
        current_weights=profile.weights,
    )
    return LearningOut(
        eligible=result.eligible,
        reason=result.reason,
        sample_size=result.sample_size,
        accepted=result.accepted,
        rejected=result.rejected,
        proposals=[{
            "dimension": p.dimension, "current": p.current, "proposed": p.proposed,
            "accepted_mean": p.accepted_mean, "rejected_mean": p.rejected_mean,
            "separation": p.separation, "delta": p.delta,
        } for p in result.proposals],
    )


@router.post("/runs/{run_id}/learning/apply")
def apply_learning(run_id: str, name: str | None = None, db: Session = Depends(get_db)):
    """Materialises the proposal as a NEW profile. The user then rescores with
    it if they want it; nothing changes underneath them."""
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    profile = db.get(ScoringProfile, run.profile_id)

    decisions = db.scalars(select(Decision).where(Decision.run_id == run_id)).all()
    result = learn_weights(
        [(d.state, d.dimension_scores or {}) for d in decisions],
        mode=profile.mode, current_weights=profile.weights,
    )
    if not result.eligible:
        raise HTTPException(400, result.reason)

    learned = ScoringProfile(
        name=name or f"{profile.name} — learned ({result.sample_size} decisions)",
        mode=profile.mode, is_builtin=False,
        weights=result.weights, targeting=dict(profile.targeting),
    )
    db.add(learned)
    db.commit()
    return {"profile_id": learned.id, "weights": learned.weights,
            "sample_size": result.sample_size}


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(run_id: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(200)
    if run_id:
        lead_ids = db.scalars(select(Lead.id).where(Lead.run_id == run_id)).all()
        stmt = select(Alert).where(Alert.lead_id.in_(lead_ids)).order_by(Alert.created_at.desc())
    return db.scalars(stmt).all()


@router.post("/runs/{run_id}/rescan")
async def rescan(run_id: str, limit: int = 100, db: Session = Depends(get_db)):
    """Re-runs the scan for a run's domains and records what changed.

    This is what turns a static export into a watchlist: a careers page
    appearing means budget moved, and 'acquired by' copy appearing means a
    target is gone.
    """
    leads = db.scalars(
        select(Lead).where(Lead.run_id == run_id, Lead.normalized_domain.is_not(None))
        .order_by(Lead.score.desc()).limit(limit)
    ).all()

    from ..core.cache import scan_cache

    changed = 0
    for lead in leads:
        domain = lead.normalized_domain
        previous = db.scalars(
            select(ScanSnapshot).where(ScanSnapshot.domain == domain)
            .order_by(ScanSnapshot.fetched_at.desc())
        ).first()

        scan_cache.backend.setex(scan_cache.key(domain), 1, "")  # force a fresh fetch
        payload = await scanner.scan(domain)
        lead.scan_payload = payload
        lead.scan_status = payload.get("status", "unknown")

        if previous is not None:
            for change in diff_snapshots(previous.payload or {}, payload):
                db.add(Alert(domain=domain, lead_id=lead.id, kind=change.kind,
                             detail=change.detail, severity=change.severity))
                changed += 1
        db.add(ScanSnapshot(domain=domain, status=lead.scan_status, payload=payload))

    db.commit()
    return {"rescanned": len(leads), "changes": changed}


@router.get("/suppression")
def list_suppression(db: Session = Depends(get_db)):
    return db.scalars(select(SuppressionEntry)).all()


@router.post("/suppression")
def add_suppression(domain: str, reason: str = "", db: Session = Depends(get_db)):
    from ..core.normalize import normalize_domain

    d = normalize_domain(domain)
    if not d:
        raise HTTPException(400, "not a valid domain")
    existing = db.get(SuppressionEntry, d)
    if existing is None:
        db.add(SuppressionEntry(domain=d, reason=reason))
        db.commit()
    return {"domain": d, "suppressed": True}


@router.delete("/suppression/{domain}")
def remove_suppression(domain: str, db: Session = Depends(get_db)):
    entry = db.get(SuppressionEntry, domain)
    if entry is None:
        raise HTTPException(404, "domain not suppressed")
    db.delete(entry)
    db.commit()
    return {"domain": domain, "suppressed": False}
