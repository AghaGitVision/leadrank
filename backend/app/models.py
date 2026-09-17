from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ScoringProfile(Base):
    __tablename__ = "scoring_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(8))  # sell | buy
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)

    # dimension key -> weight (normalised to 1.0 on save)
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    # target_industries, adjacent_industries, employee_band, revenue_band, regions
    targeting: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("scoring_profiles.id"))
    filename: Mapped[str] = mapped_column(String(255))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped[ScoringProfile] = relationship()
    leads: Mapped[list["Lead"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)

    company_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), default="")
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(160), nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revenue_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    year_founded: Mapped[int | None] = mapped_column(Integer, nullable=True)

    owner_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_status: Mapped[str] = mapped_column(String(16), default="unknown")
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    score: Mapped[float] = mapped_column(Float, default=0.0)
    band: Mapped[str] = mapped_column(String(1), default="D")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    quadrant: Mapped[str] = mapped_column(String(16), default="pass")
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)

    review_state: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    enriched: Mapped[bool] = mapped_column(Boolean, default=False)

    scan_status: Mapped[str] = mapped_column(String(24), default="not_scanned")
    scan_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    passthrough: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    merged_from: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped[Run] = relationship(back_populates="leads")
    signals: Mapped[list["LeadSignal"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_leads_run_score", "run_id", "score"),)


class LeadSignal(Base):
    """One row per evaluated signal. Makes the explanation view a query rather
    than a recomputation, and makes every point of every score auditable."""

    __tablename__ = "lead_signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)

    dimension: Mapped[str] = mapped_column(String(40))
    signal_key: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(200))
    raw_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    contribution: Mapped[float] = mapped_column(Float, default=0.0)
    forgone: Mapped[float] = mapped_column(Float, default=0.0)
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(16), default="csv")

    lead: Mapped[Lead] = relationship(back_populates="signals")


class Decision(Base):
    """Accept/reject events. Feeds the weight-learning loop (core/learning.py)."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    profile_id: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(12))
    dimension_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ScanSnapshot(Base):
    """Historical scans per domain. Diffing consecutive snapshots is what
    produces change alerts (core/monitor.py)."""

    __tablename__ = "scan_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    lead_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(String(400))
    severity: Mapped[str] = mapped_column(String(10), default="info")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SuppressionEntry(Base):
    __tablename__ = "suppression"

    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
