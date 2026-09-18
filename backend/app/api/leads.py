from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Decision, Lead, LeadSignal, Run
from ..schemas import BulkReviewIn, ExplainOut, LeadOut, ReviewIn, SignalOut

router = APIRouter(prefix="/api/v1", tags=["leads"])


@router.get("/runs/{run_id}/leads")
def list_leads(
    run_id: str,
    band: str | None = None,
    state: str | None = None,
    quadrant: str | None = None,
    scan_status: str | None = None,
    min_confidence: float = 0.0,
    q: str | None = None,
    sort: str = "score",
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(Lead).where(Lead.run_id == run_id, Lead.confidence >= min_confidence)
    if band:
        stmt = stmt.where(Lead.band.in_(band.split(",")))
    if state:
        stmt = stmt.where(Lead.review_state == state)
    if quadrant:
        stmt = stmt.where(Lead.quadrant == quadrant)
    if scan_status:
        stmt = stmt.where(Lead.scan_status == scan_status)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Lead.company_name).like(like))

    order = {
        "score": Lead.score.desc(),
        "score_asc": Lead.score.asc(),
        "confidence": Lead.confidence.desc(),
        "name": Lead.company_name.asc(),
    }.get(sort, Lead.score.desc())

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(order, Lead.id).limit(limit).offset(offset)).all()
    return {"total": total, "items": [LeadOut.model_validate(r).model_dump() for r in rows]}


@router.get("/leads/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: str, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")
    return lead


@router.get("/leads/{lead_id}/explain", response_model=ExplainOut)
def explain(lead_id: str, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")

    signals = db.scalars(select(LeadSignal).where(LeadSignal.lead_id == lead_id)).all()
    gained = sorted([s for s in signals if s.contribution > 0], key=lambda s: -s.contribution)
    lost = sorted([s for s in signals if s.present and s.forgone > 0.01], key=lambda s: -s.forgone)
    missing = [s for s in signals if not s.present]

    return ExplainOut(
        lead=LeadOut.model_validate(lead),
        dimension_scores=(lead.passthrough or {}).get("_dimension_scores", {}),
        gained=[SignalOut.model_validate(s) for s in gained],
        lost=[SignalOut.model_validate(s) for s in lost],
        missing=[SignalOut.model_validate(s) for s in missing],
        scan=lead.scan_payload or {},
        provenance=lead.provenance or {},
        merged_from=lead.merged_from or [],
    )


def _record_decision(db: Session, lead: Lead, state: str) -> None:
    if state == "pending":
        return
    run = db.get(Run, lead.run_id)
    db.add(Decision(
        run_id=lead.run_id,
        lead_id=lead.id,
        profile_id=run.profile_id if run else "",
        state=state,
        dimension_scores=(lead.passthrough or {}).get("_dimension_scores", {}),
    ))


@router.patch("/leads/{lead_id}", response_model=LeadOut)
def review_lead(lead_id: str, payload: ReviewIn, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")
    lead.review_state = payload.review_state
    _record_decision(db, lead, payload.review_state)
    db.commit()
    return lead


@router.post("/leads/bulk")
def bulk_review(payload: BulkReviewIn, db: Session = Depends(get_db)):
    leads = db.scalars(select(Lead).where(Lead.id.in_(payload.ids))).all()
    for lead in leads:
        lead.review_state = payload.review_state
        _record_decision(db, lead, payload.review_state)
    db.commit()
    return {"updated": len(leads)}


@router.post("/runs/{run_id}/undo")
def undo_last_decision(run_id: str, db: Session = Depends(get_db)):
    """Restores the most recent accept OR reject in this run back to pending
    — not just the most recent accept. Walks the append-only decision log
    newest-first and restores the first one whose lead hasn't already been
    reverted (or superseded by a later decision on that same lead), so
    repeated undo presses walk back through real history instead of only
    ever touching accepted leads."""
    decisions = db.scalars(
        select(Decision).where(Decision.run_id == run_id).order_by(Decision.created_at.desc())
    ).all()
    for decision in decisions:
        lead = db.get(Lead, decision.lead_id)
        if lead is not None and lead.review_state == decision.state:
            lead.review_state = "pending"
            db.commit()
            return {"lead_id": lead.id, "restored_from": decision.state}
    return {"lead_id": None, "restored_from": None}


@router.post("/leads/{lead_id}/enrich", response_model=LeadOut)
def enrich_lead(lead_id: str, db: Session = Depends(get_db)):
    """Marks the credit spend. In production this calls the host enrichment
    endpoint; here it records intent so the Verify-quadrant workflow is
    demonstrable end to end without spending anyone's credits."""
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")
    lead.enriched = True
    db.commit()
    return lead
