from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .api import insights, leads, profiles, runs
from .config import get_settings
from .core.cache import scan_cache
from .core.profiles_default import BUILTIN_PROFILES
from .db import SessionLocal, init_db
from .models import ScoringProfile

logging.basicConfig(
    level=logging.INFO,
    format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("leadrank")

settings = get_settings()

app = FastAPI(
    title="LeadRank",
    version="1.0.0",
    description="A qualification layer for scraped lead lists: rank, explain, triage, export.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles.router)
app.include_router(runs.router)
app.include_router(leads.router)
app.include_router(insights.router)


def seed_profiles() -> None:
    db = SessionLocal()
    try:
        existing = {p.id for p in db.scalars(select(ScoringProfile)).all()}
        for spec in BUILTIN_PROFILES:
            if spec["id"] in existing:
                continue
            db.add(ScoringProfile(**spec))
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def startup() -> None:
    init_db()
    seed_profiles()
    log.info("started env=%s scan_mode=%s cache=%s",
             settings.env, settings.scan_mode, scan_cache.kind)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "env": settings.env,
        "scan_mode": settings.scan_mode,
        "cache_backend": scan_cache.kind,
        "cache_hit_rate": scan_cache.hit_rate,
    }
