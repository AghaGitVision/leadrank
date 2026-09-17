from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..core.scoring import DEFAULT_WEIGHTS, DIMENSIONS, normalize_weights
from ..models import ScoringProfile
from ..schemas import ProfileIn, ProfileOut

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileOut])
def list_profiles(db: Session = Depends(get_db)):
    return db.scalars(select(ScoringProfile).order_by(ScoringProfile.created_at)).all()


@router.get("/schema")
def weight_schema():
    """Drives the weight sliders in the UI without hardcoding dimension names
    in the frontend."""
    return {
        mode: {
            "defaults": DEFAULT_WEIGHTS[mode],
            "dimensions": [
                {
                    "key": d.key,
                    "label": d.label,
                    "signals": [{"key": s.key, "label": s.label, "weight": s.weight}
                                for s in d.signals],
                }
                for d in dims
            ],
        }
        for mode, dims in DIMENSIONS.items()
    }


@router.post("", response_model=ProfileOut, status_code=201)
def create_profile(payload: ProfileIn, db: Session = Depends(get_db)):
    weights = payload.weights or DEFAULT_WEIGHTS[payload.mode]
    try:
        weights = normalize_weights(weights)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    profile = ScoringProfile(
        name=payload.name, mode=payload.mode, is_builtin=False,
        weights=weights, targeting=payload.targeting,
    )
    db.add(profile)
    db.commit()
    return profile


@router.patch("/{profile_id}", response_model=ProfileOut)
def update_profile(profile_id: str, payload: ProfileIn, db: Session = Depends(get_db)):
    profile = db.get(ScoringProfile, profile_id)
    if profile is None:
        raise HTTPException(404, "profile not found")
    if profile.is_builtin:
        raise HTTPException(400, "built-in profiles are read-only — clone it first")
    profile.name = payload.name
    profile.mode = payload.mode
    profile.weights = normalize_weights(payload.weights or DEFAULT_WEIGHTS[payload.mode])
    profile.targeting = payload.targeting
    db.commit()
    return profile


@router.post("/{profile_id}/clone", response_model=ProfileOut, status_code=201)
def clone_profile(profile_id: str, db: Session = Depends(get_db)):
    source = db.get(ScoringProfile, profile_id)
    if source is None:
        raise HTTPException(404, "profile not found")
    clone = ScoringProfile(
        name=f"{source.name} (copy)", mode=source.mode, is_builtin=False,
        weights=dict(source.weights), targeting=dict(source.targeting),
    )
    db.add(clone)
    db.commit()
    return clone
