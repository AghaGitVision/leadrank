"""The scoring engine.

Design rules, in priority order:

1. Deterministic. Same input, same number, every time. No model produces a score.
2. Additive and inspectable. score = sum of weighted normalized signals, and
   every point traces back to one named signal.
3. Score and confidence are separate axes. They are never multiplied together —
   doing so hides a strong-but-unverified lead behind a mediocre-but-complete
   one, and the gap between them is itself the useful output (see `quadrant`).
4. Absent is not bad. A missing signal contributes 0 and lowers confidence; it
   does not push the score down. Otherwise thin records get punished for being
   thin rather than for being wrong.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from .features import Features

SELL = "sell"
BUY = "buy"

BANDS = (("A", 82.0), ("B", 68.0), ("C", 45.0), ("D", 0.0))
CONFIDENCE_FLOOR = 0.65
SCORE_FLOOR = 68.0


# --------------------------------------------------------------------------- #
# normalizers
# --------------------------------------------------------------------------- #

def band_fit(value: float | None, lo: float, hi: float, *, softness: float = 0.6) -> float | None:
    """1.0 inside [lo, hi], gaussian falloff outside. `softness` is the fraction
    of the band width over which the score decays to ~0.37."""
    if value is None:
        return None
    if lo <= value <= hi:
        return 1.0
    width = max(hi - lo, 1e-9) * softness
    distance = lo - value if value < lo else value - hi
    return round(math.exp(-((distance / width) ** 2)), 4)


def peak_fit(value: float | None, peak: float, lo: float, hi: float) -> float | None:
    """Like band_fit but with a single optimum — used where the sweet spot is a
    point rather than a plateau (searcher target headcount)."""
    if value is None:
        return None
    if value <= 0:
        return 0.0
    spread = max(peak - lo, hi - peak, 1e-9)
    return round(math.exp(-0.5 * ((value - peak) / (spread * 0.75)) ** 2), 4)


def membership(value: str | None, exact: set[str], adjacent: set[str]) -> float | None:
    if not value:
        return None
    v = value.lower().strip()
    if any(e in v for e in exact):
        return 1.0
    if any(a in v for a in adjacent):
        return 0.6
    return 0.0


def flag(value: bool | None) -> float | None:
    return None if value is None else (1.0 if value else 0.0)


def inverted(value: float | None) -> float | None:
    return None if value is None else 1.0 - value


# --------------------------------------------------------------------------- #
# signal registry
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Signal:
    key: str
    label: str
    weight: float
    fn: Callable[[Features, dict], float | None]
    describe: Callable[[Features, dict], str] | None = None


@dataclass(frozen=True)
class Dimension:
    key: str
    label: str
    signals: tuple[Signal, ...]


DURABLE_INDUSTRIES = {
    "hvac", "plumbing", "electrical", "roofing", "landscaping", "pest control",
    "dental", "veterinary", "physical therapy", "home health", "staffing",
    "logistics", "waste", "facilities", "janitorial", "security", "machining",
    "fabrication", "industrial services", "equipment rental", "accounting",
    "insurance", "property management", "auto repair", "medical billing",
}

FRAGMENTED_INDUSTRIES = DURABLE_INDUSTRIES  # same list, different framing in copy


def _industry_fit(f: Features, cfg: dict) -> float | None:
    return membership(
        f.industry,
        {i.lower() for i in cfg.get("target_industries", [])},
        {i.lower() for i in cfg.get("adjacent_industries", [])},
    )


def _geo_fit(f: Features, cfg: dict) -> float | None:
    regions = [r.lower() for r in cfg.get("regions", [])]
    if not regions:
        return None
    haystack = " ".join(filter(None, [f.country, f.city])).lower()
    if not haystack.strip():
        return None
    return 1.0 if any(r in haystack for r in regions) else 0.0


def _employee_fit(f: Features, cfg: dict) -> float | None:
    lo, hi = cfg.get("employee_band", [10, 200])
    return band_fit(f.employee_count, lo, hi)


def _employee_peak(f: Features, cfg: dict) -> float | None:
    lo, hi = cfg.get("employee_band", [10, 100])
    peak = cfg.get("employee_peak", (lo + hi) / 2)
    return peak_fit(f.employee_count, peak, lo, hi)


def _revenue_fit(f: Features, cfg: dict) -> float | None:
    lo, hi = cfg.get("revenue_band", [1_000_000, 50_000_000])
    return band_fit(f.revenue_estimate, lo, hi)


def _tenure(f: Features, cfg: dict) -> float | None:
    years = f.years_in_business
    if years is None:
        return None
    return min(1.0, years / 20.0)


def _durable_industry(f: Features, cfg: dict) -> float | None:
    if not f.industry:
        return None
    v = f.industry.lower()
    return 1.0 if any(d in v for d in DURABLE_INDUSTRIES) else 0.25


def _site_live(f: Features, cfg: dict) -> float | None:
    if f.scan_status == "not_scanned":
        return None
    if not f.site_ok:
        return 0.0
    return 1.0 if f.scan.get("https") else 0.6


def _analytics(f: Features, cfg: dict) -> float | None:
    if not f.site_ok:
        return None
    return flag(bool(f.tech & {"google_analytics", "meta_pixel", "hubspot"}))


def _modern_stack(f: Features, cfg: dict) -> float | None:
    if not f.site_ok:
        return None
    if f.tech & {"react", "webflow", "shopify", "hubspot"}:
        return 1.0
    if f.tech & {"wordpress", "squarespace", "wix"}:
        return 0.5
    return 0.0


def _site_freshness(f: Features, cfg: dict) -> float | None:
    gap = f.site_age_gap
    if gap is None:
        return None
    return max(0.0, 1.0 - gap / 6.0)


def _hiring(f: Features, cfg: dict) -> float | None:
    if not f.site_ok:
        return None
    return flag(bool(f.scan.get("has_careers")))


def _publishing(f: Features, cfg: dict) -> float | None:
    if not f.site_ok:
        return None
    return flag(bool(f.scan.get("has_blog")))


def _social_presence(f: Features, cfg: dict) -> float | None:
    if not f.site_ok:
        return None
    return min(1.0, len(f.socials) / 3.0)


def _email_signal(f: Features, cfg: dict) -> float | None:
    return f.email_score


def _phone_signal(f: Features, cfg: dict) -> float | None:
    if f.phone:
        return 1.0
    return 0.5 if f.scan.get("phones") else (None if not f.site_ok else 0.0)


def _linkedin_signal(f: Features, cfg: dict) -> float | None:
    if f.linkedin_url:
        return 1.0
    if "linkedin" in f.socials:
        return 0.6
    return None if not f.site_ok else 0.0


def _seniority_signal(f: Features, cfg: dict) -> float | None:
    return f.seniority


def _completeness(f: Features, cfg: dict) -> float | None:
    fields = [f.domain, f.industry, f.employee_count, f.revenue_estimate,
              f.email, f.phone, f.city, f.country]
    return round(sum(1 for x in fields if x not in (None, "")) / len(fields), 4)


def _scan_success(f: Features, cfg: dict) -> float | None:
    if f.scan_status == "not_scanned":
        return None
    return 1.0 if f.site_ok else 0.2


# --- buy-mode specific ------------------------------------------------------

def _owner_operated(f: Features, cfg: dict) -> float | None:
    if not f.owner_name:
        return None
    return 1.0 if f.owner_matches_company else 0.7


def _family_owned(f: Features, cfg: dict) -> float | None:
    if not f.site_ok:
        return None
    if "family_owned" in f.markers or "employee_owned" in f.markers:
        return 1.0
    return 0.0


def _not_pe_backed(f: Features, cfg: dict) -> float | None:
    if not f.site_ok:
        return None
    return 0.0 if "pe_backed" in f.markers else 1.0


def _modernization_upside(f: Features, cfg: dict) -> float | None:
    """Inverted digital maturity, gated on the business being alive.

    A dated site with no analytics is the value-creation thesis: a good business
    with no technology. But the gate matters — an unreachable site is a dead
    business, not an opportunity, so it scores 0 rather than maximum upside.
    """
    if not f.site_ok:
        return None
    points, total = 0.0, 0.0
    total += 1;  points += 0.0 if f.tech & {"google_analytics", "meta_pixel", "hubspot"} else 1.0
    total += 1;  points += 0.0 if f.scan.get("has_cart") or "booking" in f.markers else 1.0
    total += 1;  points += 0.0 if f.tech & {"react", "webflow", "shopify"} else 1.0
    total += 1;  points += min(1.0, (f.site_age_gap or 0) / 5.0)
    total += 1;  points += 1.0 - min(1.0, len(f.socials) / 3.0)
    return round(points / total, 4)


def _recurring_revenue(f: Features, cfg: dict) -> float | None:
    if not f.site_ok:
        return None
    return flag("recurring_revenue" in f.markers)


def _multi_location(f: Features, cfg: dict) -> float | None:
    if not f.site_ok:
        return None
    return flag("multi_location" in f.markers)


def _fragmented_market(f: Features, cfg: dict) -> float | None:
    if not f.industry:
        return None
    v = f.industry.lower()
    return 1.0 if any(d in v for d in FRAGMENTED_INDUSTRIES) else 0.2


# --------------------------------------------------------------------------- #
# dimension definitions
# --------------------------------------------------------------------------- #

SELL_DIMENSIONS: tuple[Dimension, ...] = (
    Dimension("firmographic_fit", "Firmographic fit", (
        Signal("industry_match", "Industry in target set", 0.40, _industry_fit),
        Signal("employee_band", "Headcount inside target band", 0.25, _employee_fit),
        Signal("revenue_band", "Revenue estimate inside target band", 0.20, _revenue_fit),
        Signal("geography", "Located in a target region", 0.15, _geo_fit),
    )),
    Dimension("contactability", "Contactability", (
        Signal("email_quality", "Deliverable email address", 0.40, _email_signal),
        Signal("phone", "Direct phone number", 0.20, _phone_signal),
        Signal("linkedin", "LinkedIn company page", 0.15, _linkedin_signal),
        Signal("seniority", "Named contact with decision authority", 0.25, _seniority_signal),
    )),
    Dimension("digital_maturity", "Digital maturity", (
        Signal("site_live", "Site reachable over HTTPS", 0.30, _site_live),
        Signal("analytics", "Analytics or tag manager in use", 0.25, _analytics),
        Signal("modern_stack", "Modern web stack", 0.25, _modern_stack),
        Signal("site_freshness", "Site maintained recently", 0.20, _site_freshness),
    )),
    Dimension("growth_signals", "Growth signals", (
        Signal("hiring", "Careers or hiring page", 0.40, _hiring),
        Signal("publishing", "Active blog or news section", 0.25, _publishing),
        Signal("social_presence", "Multiple active social profiles", 0.35, _social_presence),
    )),
    Dimension("data_confidence", "Record quality", (
        Signal("completeness", "Field completeness", 0.60, _completeness),
        Signal("scan_success", "Web signals collected", 0.40, _scan_success),
    )),
)

BUY_DIMENSIONS: tuple[Dimension, ...] = (
    Dimension("size_durability", "Size & durability", (
        Signal("employee_band", "Headcount in acquisition sweet spot", 0.35, _employee_peak),
        Signal("revenue_band", "Revenue estimate inside target band", 0.25, _revenue_fit),
        Signal("tenure", "Years in business", 0.25, _tenure),
        Signal("durable_industry", "Non-cyclical service industry", 0.15, _durable_industry),
    )),
    Dimension("succession", "Succession signals", (
        Signal("owner_operated", "Owner-operated business", 0.40, _owner_operated),
        Signal("family_owned", "Family or employee owned", 0.25, _family_owned),
        Signal("not_pe_backed", "No institutional backing detected", 0.35, _not_pe_backed),
    )),
    Dimension("modernization_upside", "Modernization upside", (
        Signal("upside_index", "Under-digitized relative to its market", 1.00, _modernization_upside),
    )),
    Dimension("market_position", "Market position", (
        Signal("fragmented_market", "Fragmented, roll-up friendly market", 0.35, _fragmented_market),
        Signal("recurring_revenue", "Contract or maintenance revenue language", 0.35, _recurring_revenue),
        Signal("multi_location", "Multiple locations or branches", 0.30, _multi_location),
    )),
    Dimension("data_confidence", "Record quality", (
        Signal("completeness", "Field completeness", 0.60, _completeness),
        Signal("scan_success", "Web signals collected", 0.40, _scan_success),
    )),
)

DIMENSIONS = {SELL: SELL_DIMENSIONS, BUY: BUY_DIMENSIONS}

DEFAULT_WEIGHTS = {
    SELL: {
        "firmographic_fit": 0.30,
        "contactability": 0.25,
        "digital_maturity": 0.20,
        "growth_signals": 0.15,
        "data_confidence": 0.10,
    },
    BUY: {
        "size_durability": 0.30,
        "succession": 0.25,
        "modernization_upside": 0.20,
        "market_position": 0.15,
        "data_confidence": 0.10,
    },
}


# --------------------------------------------------------------------------- #
# result types
# --------------------------------------------------------------------------- #

@dataclass
class Contribution:
    dimension: str
    dimension_label: str
    signal_key: str
    label: str
    normalized: float | None
    weight: float
    contribution: float
    forgone: float
    present: bool


@dataclass
class ScoreResult:
    score: float
    band: str
    confidence: float
    quadrant: str
    dimension_scores: dict[str, float]
    contributions: list[Contribution]

    @property
    def gained(self) -> list[Contribution]:
        return sorted([c for c in self.contributions if c.contribution > 0],
                      key=lambda c: -c.contribution)

    @property
    def lost(self) -> list[Contribution]:
        return sorted([c for c in self.contributions if c.forgone > 0.01],
                      key=lambda c: -c.forgone)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, w) for w in weights.values())
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    return {k: round(max(0.0, v) / total, 6) for k, v in weights.items()}


def band_for(score: float) -> str:
    for name, floor in BANDS:
        if score >= floor:
            return name
    return "D"


def quadrant_for(score: float, confidence: float) -> str:
    if score >= SCORE_FLOOR:
        return "act" if confidence >= CONFIDENCE_FLOOR else "verify"
    return "pass" if confidence >= CONFIDENCE_FLOOR else "recheck"


def score_lead(features: Features, *, mode: str, weights: dict[str, float],
               targeting: dict) -> ScoreResult:
    dims = DIMENSIONS[mode]
    weights = normalize_weights({d.key: weights.get(d.key, DEFAULT_WEIGHTS[mode][d.key]) for d in dims})

    contributions: list[Contribution] = []
    dimension_scores: dict[str, float] = {}
    total = 0.0
    covered_weight = 0.0
    total_weight = 0.0

    for dim in dims:
        dim_weight = weights[dim.key]
        evaluated = [(s, s.fn(features, targeting)) for s in dim.signals]
        present_weight = sum(s.weight for s, v in evaluated if v is not None)

        dim_value = 0.0
        for sig, value in evaluated:
            total_weight += dim_weight * sig.weight
            if value is None:
                contributions.append(Contribution(
                    dim.key, dim.label, sig.key, sig.label, None, 0.0, 0.0, 0.0, False))
                continue

            covered_weight += dim_weight * sig.weight
            share = sig.weight / present_weight if present_weight else 0.0
            points = dim_weight * share * value * 100
            forgone = dim_weight * share * (1.0 - value) * 100
            dim_value += share * value
            contributions.append(Contribution(
                dim.key, dim.label, sig.key, sig.label, round(value, 4),
                round(dim_weight * share, 6), round(points, 2), round(forgone, 2), True))

        dimension_scores[dim.key] = round(dim_value, 4)
        total += dim_weight * dim_value * 100

    score = round(min(100.0, max(0.0, total)), 1)
    confidence = round(covered_weight / total_weight, 4) if total_weight else 0.0

    return ScoreResult(
        score=score,
        band=band_for(score),
        confidence=confidence,
        quadrant=quadrant_for(score, confidence),
        dimension_scores=dimension_scores,
        contributions=contributions,
    )
