from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProfileIn(BaseModel):
    name: str
    mode: str = Field(pattern="^(sell|buy)$")
    weights: dict[str, float] = {}
    targeting: dict = {}


class ProfileOut(BaseModel):
    id: str
    name: str
    mode: str
    is_builtin: bool
    weights: dict[str, float]
    targeting: dict

    class Config:
        from_attributes = True


class RunOut(BaseModel):
    id: str
    profile_id: str
    filename: str
    row_count: int
    status: str
    progress: float
    stats: dict
    started_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True


class LeadOut(BaseModel):
    id: str
    company_name: str
    domain: str | None
    country: str | None
    city: str | None
    industry: str | None
    employee_count: int | None
    revenue_estimate: float | None
    owner_name: str | None
    email: str | None
    email_status: str
    phone: str | None
    linkedin_url: str | None
    score: float
    band: str
    confidence: float
    quadrant: str
    narrative: str | None
    review_state: str
    enriched: bool
    scan_status: str

    class Config:
        from_attributes = True


class SignalOut(BaseModel):
    dimension: str
    signal_key: str
    label: str
    normalized_value: float | None
    weight: float
    contribution: float
    forgone: float
    present: bool
    source: str

    class Config:
        from_attributes = True


class ExplainOut(BaseModel):
    lead: LeadOut
    dimension_scores: dict[str, float]
    gained: list[SignalOut]
    lost: list[SignalOut]
    missing: list[SignalOut]
    scan: dict
    provenance: dict
    merged_from: list


class ReviewIn(BaseModel):
    review_state: str = Field(pattern="^(pending|accepted|rejected)$")


class BulkReviewIn(BaseModel):
    ids: list[str]
    review_state: str = Field(pattern="^(pending|accepted|rejected)$")


class RescoreIn(BaseModel):
    profile_id: str | None = None
    weights: dict[str, float] | None = None
    targeting: dict | None = None


class AlertOut(BaseModel):
    id: str
    domain: str
    lead_id: str | None
    kind: str
    detail: str
    severity: str
    created_at: datetime

    class Config:
        from_attributes = True


class WeightProposalOut(BaseModel):
    dimension: str
    current: float
    proposed: float
    accepted_mean: float
    rejected_mean: float
    separation: float
    delta: float


class LearningOut(BaseModel):
    eligible: bool
    reason: str
    sample_size: int
    accepted: int
    rejected: int
    proposals: list[WeightProposalOut]
