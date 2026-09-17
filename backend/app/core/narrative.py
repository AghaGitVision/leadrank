"""The one place a language model is allowed near this product, and even here it
only rewrites a sentence that has already been composed deterministically from
the top contributions. If the API key is absent or the call fails, the
deterministic sentence ships. The number is never touched."""

from __future__ import annotations

import httpx

from ..config import get_settings
from .features import Features
from .scoring import BUY, ScoreResult

ANGLES = {
    "modernization_upside": "no digital booking or analytics — lead with operational leverage, not price",
    "succession": "owner-operated with long tenure — approach as a stewardship conversation",
    "size_durability": "stable headcount and revenue in the target band — lead with continuity",
    "market_position": "contract revenue in a fragmented market — lead with roll-up economics",
    "contactability": "decision-maker reachable directly — go straight to the owner",
    "firmographic_fit": "textbook profile fit — lead with a peer reference in the same vertical",
    "digital_maturity": "already running a modern stack — lead with integration, not replacement",
    "growth_signals": "actively hiring and publishing — lead with scale pressure",
    "data_confidence": "record is thin — verify before investing outreach time",
}


def deterministic_summary(features: Features, result: ScoreResult, mode: str) -> str:
    top = result.gained[:3]
    if not top:
        return "Not enough signal to summarise. Verify the record before acting."

    dims = []
    for c in top:
        if c.dimension not in dims:
            dims.append(c.dimension)
    lead_dim = dims[0]

    descriptor = []
    if features.employee_count:
        descriptor.append(f"{features.employee_count} staff")
    if features.industry:
        descriptor.append(features.industry.lower())
    if features.years_in_business:
        descriptor.append(f"{features.years_in_business} yrs in business")
    head = ", ".join(descriptor) or features.company_name

    angle = ANGLES.get(lead_dim, "review the signal breakdown before outreach")
    verb = "Acquisition angle" if mode == BUY else "Outreach angle"
    caveat = ""
    if result.quadrant == "verify":
        caveat = " Confidence is low — enrich before spending outreach time."
    return f"{head}. {verb}: {angle}.{caveat}"


async def llm_summary(features: Features, result: ScoreResult, mode: str) -> tuple[str, bool]:
    """-> (text, was_generated). Falls back silently; a failed call must never
    block a run."""
    settings = get_settings()
    base = deterministic_summary(features, result, mode)
    if not settings.anthropic_api_key:
        return base, False

    top = "\n".join(f"- {c.label}: +{c.contribution}" for c in result.gained[:4])
    prompt = (
        "Rewrite this lead summary as one sentence of at most 28 words for a "
        f"{'searcher evaluating an acquisition' if mode == BUY else 'sales rep planning outreach'}. "
        "Use only the facts given. Do not invent numbers. Plain language, no adjectives for their own sake.\n\n"
        f"Company: {features.company_name}\nScore: {result.score} ({result.band})\n"
        f"Top signals:\n{top}\n\nDraft: {base}"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.narrative_model,
                    "max_tokens": 120,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            r.raise_for_status()
            text = "".join(
                block.get("text", "") for block in r.json().get("content", [])
                if block.get("type") == "text"
            ).strip()
            return (text or base), bool(text)
    except Exception:
        return base, False
