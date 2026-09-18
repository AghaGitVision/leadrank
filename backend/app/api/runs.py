from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core import ingest
from ..core.exporter import to_csv
from ..core.pipeline import apply_score, attach_narratives, execute_run
from ..core.scoring import normalize_weights
from ..core.sources import CsvSource, LeadSource, SaaSquatchSource
from ..db import SessionLocal, get_db
from ..models import Lead, LeadSignal, Run, ScoringProfile
from ..schemas import RescoreIn, RunOut, SearchRunIn

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.post("/preview")
async def preview_columns(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    report = ingest.preview(content)
    return {
        "mapping": report.mapping,
        "unmapped": report.unmapped,
        "missing_required": report.missing_required,
        "samples": report.samples,
    }


def _run_pipeline(run_id: str, source: LeadSource, fetch_params: dict) -> None:
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run is None:
            return
        asyncio.run(execute_run(db, run, source, **fetch_params))
    except Exception as exc:  # surface failures in the run record, never swallow
        run = db.get(Run, run_id)
        if run is not None:
            run.status = "failed"
            run.stats = {**(run.stats or {}), "error": str(exc)}
            db.commit()
    finally:
        db.close()


@router.post("", response_model=RunOut, status_code=201)
async def create_run(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    profile_id: str = Form(...),
    mapping: str | None = Form(None),
    check_mx: bool = Form(False),
    db: Session = Depends(get_db),
):
    profile = db.get(ScoringProfile, profile_id)
    if profile is None:
        raise HTTPException(404, "profile not found")

    content = (await file.read()).decode("utf-8-sig", errors="replace")
    parsed_mapping = json.loads(mapping) if mapping else None

    run = Run(profile_id=profile_id, filename=file.filename or "upload.csv", status="pending")
    db.add(run)
    db.commit()

    source = CsvSource(content, parsed_mapping, check_mx)
    background.add_task(_run_pipeline, run.id, source, {})
    return run


@router.post("/search", response_model=RunOut, status_code=201)
async def create_run_from_search(
    payload: SearchRunIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Scores a SaaSquatch search result set through the same pipeline a CSV
    upload uses — the search-time path sketched in `core/sources.py`, wired
    up rather than left as a stub."""
    profile = db.get(ScoringProfile, payload.profile_id)
    if profile is None:
        raise HTTPException(404, "profile not found")

    settings = get_settings()
    if not settings.saasquatch_api_key:
        raise HTTPException(
            400,
            "SaaSquatch search-time scoring requires LEADRANK_SAASQUATCH_API_KEY to be "
            "set — this integration seam is wired but uncredentialed in this environment.",
        )

    fetch_params = {
        "industry": payload.industry,
        "country": payload.country,
        "min_employees": payload.min_employees,
        "max_employees": payload.max_employees,
        "limit": payload.limit,
    }
    label = payload.industry or payload.country or "search"
    run = Run(profile_id=payload.profile_id, filename=f"saasquatch:{label}", status="pending")
    db.add(run)
    db.commit()

    source = SaaSquatchSource(api_key=settings.saasquatch_api_key)
    background.add_task(_run_pipeline, run.id, source, fetch_params)
    return run


@router.get("", response_model=list[RunOut])
def list_runs(db: Session = Depends(get_db)):
    return db.scalars(select(Run).order_by(Run.started_at.desc()).limit(50)).all()


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run


@router.get("/{run_id}/events")
async def run_events(run_id: str):
    """SSE progress. The client watches this instead of polling, so a 400-row
    scan streams its progress instead of blocking the page."""

    async def stream():
        last = None
        for _ in range(600):  # 5 min ceiling
            db = SessionLocal()
            try:
                run = db.get(Run, run_id)
                if run is None:
                    yield "event: error\ndata: {}\n\n"
                    return
                payload = {"status": run.status, "progress": round(run.progress, 3),
                           "row_count": run.row_count, "stats": run.stats}
                if payload != last:
                    yield f"data: {json.dumps(payload)}\n\n"
                    last = payload
                if run.status in ("complete", "failed"):
                    return
            finally:
                db.close()
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{run_id}/rescore", response_model=RunOut)
def rescore(run_id: str, payload: RescoreIn, db: Session = Depends(get_db)):
    """Replays cached signals through new weights. No network, no refetch —
    which is what makes live weight tuning viable."""
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")

    profile = db.get(ScoringProfile, payload.profile_id or run.profile_id)
    if profile is None:
        raise HTTPException(404, "profile not found")

    if payload.weights or payload.targeting:
        # ephemeral profile: tune without persisting until the user saves
        profile = ScoringProfile(
            id=profile.id, name=profile.name, mode=profile.mode,
            is_builtin=profile.is_builtin,
            weights=normalize_weights(payload.weights) if payload.weights else profile.weights,
            targeting=payload.targeting or profile.targeting,
        )

    leads = db.scalars(select(Lead).where(Lead.run_id == run_id)).all()
    for lead in leads:
        apply_score(db, lead, profile)

    bands: dict[str, int] = {}
    quadrants: dict[str, int] = {}
    for lead in leads:
        bands[lead.band] = bands.get(lead.band, 0) + 1
        quadrants[lead.quadrant] = quadrants.get(lead.quadrant, 0) + 1

    run.profile_id = payload.profile_id or run.profile_id
    run.stats = {**(run.stats or {}), "bands": bands, "quadrants": quadrants, "rescored": True}
    db.commit()
    return run


@router.post("/{run_id}/narratives")
async def generate_narratives(run_id: str, limit: int = 25, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    written = await attach_narratives(db, run, limit=limit)
    return {"rewritten": written, "model_used": written > 0}


@router.get("/{run_id}/export", response_class=PlainTextResponse)
def export_run(run_id: str, format: str = "csv", state: str = "accepted",
               db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")

    q = select(Lead).where(Lead.run_id == run_id)
    if state != "all":
        q = q.where(Lead.review_state == state)
    leads = db.scalars(q.order_by(Lead.score.desc())).all()

    rows = []
    for lead in leads:
        signals = db.scalars(
            select(LeadSignal)
            .where(LeadSignal.lead_id == lead.id)
            .order_by(LeadSignal.contribution.desc())
            .limit(3)
        ).all()
        rows.append({
            **{c: getattr(lead, c) for c in (
                "company_name", "domain", "industry", "city", "country",
                "employee_count", "revenue_estimate", "owner_name", "email",
                "email_status", "phone", "linkedin_url", "score", "band",
                "confidence", "quadrant", "narrative")},
            "top_signals": " | ".join(f"{s.label} (+{s.contribution})" for s in signals),
            "passthrough": lead.passthrough or {},
        })

    csv_text = to_csv(rows, preset=format)
    filename = f"leadrank_{run_id[:8]}_{state}.csv"
    return PlainTextResponse(
        csv_text, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
