"""Weight learning from triage decisions.

Deliberately not a black box. For each dimension we compute the mean dimension
score among accepted leads and among rejected leads. The separation between
those two means is how much that dimension actually predicted the user's own
judgement. Dimensions that separated well get more weight; dimensions the user
ignored get less.

Properties that matter more than accuracy here:
  * explainable  — the proposed change is shown as a table with the evidence
  * bounded      — no weight moves more than `learning_max_shift` in one pass
  * opt-in       — it proposes a profile, it never mutates the active one
  * gated        — nothing is proposed below `learning_min_decisions` samples
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import get_settings
from .scoring import DEFAULT_WEIGHTS, normalize_weights


@dataclass
class WeightProposal:
    dimension: str
    current: float
    proposed: float
    accepted_mean: float
    rejected_mean: float
    separation: float

    @property
    def delta(self) -> float:
        return round(self.proposed - self.current, 4)


@dataclass
class LearningResult:
    eligible: bool
    reason: str
    sample_size: int
    accepted: int
    rejected: int
    proposals: list[WeightProposal]

    @property
    def weights(self) -> dict[str, float]:
        return {p.dimension: p.proposed for p in self.proposals}


def learn_weights(
    decisions: list[tuple[str, dict[str, float]]],
    *,
    mode: str,
    current_weights: dict[str, float] | None = None,
) -> LearningResult:
    """`decisions` is a list of (state, dimension_scores)."""
    settings = get_settings()
    current = normalize_weights(current_weights or DEFAULT_WEIGHTS[mode])

    accepted = [d for s, d in decisions if s == "accepted"]
    rejected = [d for s, d in decisions if s == "rejected"]
    n = len(accepted) + len(rejected)

    if n < settings.learning_min_decisions:
        return LearningResult(
            False, f"needs {settings.learning_min_decisions} decisions, has {n}",
            n, len(accepted), len(rejected), [])
    if not accepted or not rejected:
        return LearningResult(
            False, "needs at least one accept and one reject", n,
            len(accepted), len(rejected), [])

    def mean(rows: list[dict[str, float]], key: str) -> float:
        vals = [r.get(key, 0.0) for r in rows]
        return sum(vals) / len(vals) if vals else 0.0

    separations: dict[str, float] = {}
    stats: dict[str, tuple[float, float]] = {}
    for dim in current:
        a, r = mean(accepted, dim), mean(rejected, dim)
        stats[dim] = (a, r)
        separations[dim] = max(0.0, a - r)  # only reward positive discrimination

    total_sep = sum(separations.values())
    max_shift = settings.learning_max_shift

    raw: dict[str, float] = {}
    for dim, w in current.items():
        if total_sep <= 0:
            raw[dim] = w
            continue
        evidence_share = separations[dim] / total_sep
        blended = (1 - max_shift) * w + max_shift * evidence_share
        raw[dim] = blended

    proposed = normalize_weights(raw)

    proposals = [
        WeightProposal(
            dimension=dim,
            current=round(current[dim], 4),
            proposed=round(proposed[dim], 4),
            accepted_mean=round(stats[dim][0], 4),
            rejected_mean=round(stats[dim][1], 4),
            separation=round(separations[dim], 4),
        )
        for dim in sorted(current, key=lambda d: -separations[d])
    ]

    return LearningResult(True, "ok", n, len(accepted), len(rejected), proposals)
