"""End-to-end API walkthrough. No UI needed.

Exercises the same path a reviewer would click through by hand: upload the
seed CSV, wait for scoring, inspect the top lead's explanation, prove the
buy/sell inversion by rescoring in place (no refetch), and export the
accepted list. Every number printed here is read straight from the running
API — nothing here is precomputed or faked for the demo.

Usage (with the backend already running on :8000, per the README):

    cd backend
    python scripts/api_demo.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

API_BASE = os.environ.get("LEADRANK_API_BASE", "http://localhost:8000")
SEED_CSV = Path(__file__).resolve().parent.parent / "app" / "data" / "seed_leads.csv"


def rule(title: str) -> None:
    print(f"\n{'─' * 72}\n{title}\n{'─' * 72}")


def money(v: float | None) -> str:
    if not v:
        return "—"
    return f"${v / 1_000_000:.1f}M" if v >= 1_000_000 else f"${v:,.0f}"


def main() -> None:
    client = httpx.Client(base_url=API_BASE, timeout=30.0)

    rule("1. Health check")
    health = client.get("/health").json()
    print(health)
    if health.get("status") != "ok":
        sys.exit("API is not healthy — is `uvicorn app.main:app` running?")

    rule("2. Scoring profiles (built-in)")
    profiles = client.get("/api/v1/profiles").json()
    buy_profile = next(p for p in profiles if p["mode"] == "buy")
    sell_profile = next(p for p in profiles if p["mode"] == "sell")
    for p in profiles:
        print(f"  {p['id']:<28} {p['name']}")

    if not SEED_CSV.exists():
        sys.exit(f"Seed CSV not found at {SEED_CSV} — run scripts/generate_seed.py first.")

    rule(f"3. Upload {SEED_CSV.name} under Buy mode: '{buy_profile['name']}'")
    with SEED_CSV.open("rb") as fh:
        run = client.post(
            "/api/v1/runs",
            files={"file": (SEED_CSV.name, fh, "text/csv")},
            data={"profile_id": buy_profile["id"]},
        ).json()
    run_id = run["id"]
    print(f"  run_id = {run_id}")

    rule("4. Waiting for ingest → scan → score to complete")
    while True:
        run = client.get(f"/api/v1/runs/{run_id}").json()
        print(f"  {run['status']:<10} progress={run['progress']:.0%}")
        if run["status"] in ("complete", "failed"):
            break
        time.sleep(0.4)
    if run["status"] != "complete":
        sys.exit(f"Run failed: {run['stats'].get('error')}")

    stats = run["stats"]
    print(f"\n  {stats['input_rows']} rows in, "
          f"{stats['exact_merges'] + stats['fuzzy_merges']} duplicates merged, "
          f"{run['row_count']} scored")
    print(f"  bands: {stats['bands']}   quadrants: {stats['quadrants']}")

    rule("5. Top 5 leads, Buy mode")
    top = client.get(f"/api/v1/runs/{run_id}/leads", params={"limit": 5, "sort": "score"}).json()
    for lead in top["items"]:
        print(f"  {lead['score']:>5.1f}  {lead['band']}  {lead['company_name']:<32} "
              f"{lead['industry'] or '':<20} conf={lead['confidence']:.0%}")

    best = top["items"][0]
    rule(f"6. Why '{best['company_name']}' scored {best['score']} in Buy mode")
    explain = client.get(f"/api/v1/leads/{best['id']}/explain").json()
    for s in explain["gained"][:6]:
        print(f"  +{s['contribution']:>5.1f}  {s['label']}")
    print(f"\n  {best['narrative']}")

    rule("7. The core claim: rescore the SAME run under Sell mode — no refetch")
    started = time.time()
    client.post(f"/api/v1/runs/{run_id}/rescore", json={"profile_id": sell_profile["id"]})
    elapsed_ms = (time.time() - started) * 1000
    sell_lead = client.get(f"/api/v1/runs/{run_id}/leads", params={"q": best["company_name"]}).json()
    sell_view = sell_lead["items"][0]
    print(f"  '{best['company_name']}':  Buy={best['score']} ({best['band']})  ->  "
          f"Sell={sell_view['score']} ({sell_view['band']})")
    print(f"  Same cached scan payload, {run['row_count']} leads rescored in {elapsed_ms:.0f}ms — "
          f"zero network calls.")

    rule("8. Rescore back to Buy mode and export the accepted shortlist")
    client.post(f"/api/v1/runs/{run_id}/rescore", json={"profile_id": buy_profile["id"]})
    client.patch(f"/api/v1/leads/{best['id']}", json={"review_state": "accepted"})
    csv_text = client.get(f"/api/v1/runs/{run_id}/export",
                           params={"format": "hubspot", "state": "accepted"}).text
    out_path = Path("demo_export.csv")
    out_path.write_text(csv_text)
    print(f"  wrote {out_path.resolve()} ({len(csv_text.splitlines())} lines, HubSpot column preset)")

    rule("9. Weight learning is gated until there's enough signal")
    learning = client.get(f"/api/v1/runs/{run_id}/learning").json()
    print(f"  eligible={learning['eligible']}  reason='{learning['reason']}'  "
          f"(has {learning['sample_size']} decisions so far)")

    rule("Done")
    print(f"  Full run in the UI: http://localhost:3000/runs/{run_id}")
    print(f"  (or :3001 if your frontend fell back to that port)")


if __name__ == "__main__":
    main()
