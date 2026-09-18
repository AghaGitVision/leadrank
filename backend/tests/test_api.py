"""API-level integration tests.

test_core.py exercises the scoring/dedupe/validation functions directly and
never touches a request, the database, or the pipeline. These tests close
that gap: they drive the FastAPI app exactly as the frontend does — upload a
CSV, wait for the background pipeline to score it, then walk triage, explain,
rescore, export, and suppression through real HTTP calls against a real
(throwaway) SQLite database. No network egress: LEADRANK_SCAN_MODE=offline is
set in conftest.py, same as CI.
"""

from __future__ import annotations

CSV_CONTENT = (
    "Company Name,Website,Industry,City,Country,Employees,Annual Revenue,Owner,Email,Phone\n"
    "Delgado HVAC,delgadohvac.com,HVAC,Austin,United States,26,4200000,Maria Delgado,"
    "maria@delgadohvac.com,+15125550101\n"
    "Summit Plumbing,summitplumbing.com,Plumbing,Dallas,United States,40,6500000,James Renner,"
    "james@summitplumbing.com,+15125550102\n"
    "Riverside Electrical,riverside-electrical.com,Electrical,Houston,United States,15,3100000,"
    "Nancy Whitfield,nancy@riverside-electrical.com,+15125550103\n"
)

SELL_PROFILE_ID = "builtin_sell_smb_saas"


def _create_run(client) -> dict:
    resp = client.post(
        "/api/v1/runs",
        files={"file": ("leads.csv", CSV_CONTENT, "text/csv")},
        data={"profile_id": SELL_PROFILE_ID},
    )
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["id"]

    # BackgroundTasks run synchronously under TestClient (the response is only
    # sent once the background task's thread completes), so the run is
    # already scored by the time control returns here.
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "complete", run
    return run


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_profiles_are_seeded_on_startup(client):
    resp = client.get("/api/v1/profiles")
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert SELL_PROFILE_ID in ids

    schema = client.get("/api/v1/profiles/schema").json()
    assert "sell" in schema and "buy" in schema
    assert "dimensions" in schema["sell"]


def test_run_not_found_returns_404(client):
    resp = client.get("/api/v1/runs/does-not-exist")
    assert resp.status_code == 404


def test_create_run_scores_uploaded_leads(client):
    run = _create_run(client)
    assert run["row_count"] == 3
    assert run["stats"]["input_rows"] == 3

    leads = client.get(f"/api/v1/runs/{run['id']}/leads").json()
    assert leads["total"] == 3
    assert len(leads["items"]) == 3
    for lead in leads["items"]:
        assert lead["band"] in {"A", "B", "C", "D"}
        assert lead["review_state"] == "pending"


def test_explain_returns_signal_waterfall(client):
    run = _create_run(client)
    lead_id = client.get(f"/api/v1/runs/{run['id']}/leads").json()["items"][0]["id"]

    resp = client.get(f"/api/v1/leads/{lead_id}/explain")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lead"]["id"] == lead_id
    assert isinstance(body["gained"], list)
    assert isinstance(body["dimension_scores"], dict)


def test_review_and_bulk_review_round_trip(client):
    run = _create_run(client)
    lead_ids = [l["id"] for l in client.get(f"/api/v1/runs/{run['id']}/leads").json()["items"]]

    single, rest = lead_ids[0], lead_ids[1:]

    resp = client.patch(f"/api/v1/leads/{single}", json={"review_state": "accepted"})
    assert resp.status_code == 200
    assert resp.json()["review_state"] == "accepted"

    resp = client.post(
        "/api/v1/leads/bulk", json={"ids": rest, "review_state": "rejected"}
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == len(rest)

    accepted = client.get(f"/api/v1/runs/{run['id']}/leads", params={"state": "accepted"}).json()
    rejected = client.get(f"/api/v1/runs/{run['id']}/leads", params={"state": "rejected"}).json()
    assert [l["id"] for l in accepted["items"]] == [single]
    assert {l["id"] for l in rejected["items"]} == set(rest)


def test_undo_restores_most_recent_decision_regardless_of_type(client):
    """Undo must walk back through real history — accept, then reject, then
    undo should restore the reject (the more recent action), not silently
    fall back to touching the accepted lead just because it's the only one
    undo used to know how to find."""
    run = _create_run(client)
    a, b, c = (l["id"] for l in client.get(f"/api/v1/runs/{run['id']}/leads").json()["items"])

    client.patch(f"/api/v1/leads/{a}", json={"review_state": "accepted"})
    client.patch(f"/api/v1/leads/{b}", json={"review_state": "rejected"})

    resp = client.post(f"/api/v1/runs/{run['id']}/undo")
    assert resp.status_code == 200
    assert resp.json() == {"lead_id": b, "restored_from": "rejected"}
    assert client.get(f"/api/v1/leads/{b}").json()["review_state"] == "pending"
    assert client.get(f"/api/v1/leads/{a}").json()["review_state"] == "accepted"

    resp = client.post(f"/api/v1/runs/{run['id']}/undo")
    assert resp.json() == {"lead_id": a, "restored_from": "accepted"}
    assert client.get(f"/api/v1/leads/{a}").json()["review_state"] == "pending"

    resp = client.post(f"/api/v1/runs/{run['id']}/undo")
    assert resp.json() == {"lead_id": None, "restored_from": None}


def test_rescore_is_ephemeral_unless_saved(client):
    run = _create_run(client)
    before = client.get("/api/v1/profiles").json()
    before_weights = next(p["weights"] for p in before if p["id"] == run["profile_id"])

    resp = client.post(
        f"/api/v1/runs/{run['id']}/rescore",
        json={"weights": {"fit": 0.9}},
    )
    assert resp.status_code == 200
    assert resp.json()["stats"]["rescored"] is True

    after = client.get("/api/v1/profiles").json()
    after_weights = next(p["weights"] for p in after if p["id"] == run["profile_id"])
    assert after_weights == before_weights, "an inline rescore weight override must never mutate the stored profile"


def test_export_includes_crm_field_mapping(client):
    run = _create_run(client)
    lead_id = client.get(f"/api/v1/runs/{run['id']}/leads").json()["items"][0]["id"]
    client.patch(f"/api/v1/leads/{lead_id}", json={"review_state": "accepted"})

    resp = client.get(f"/api/v1/runs/{run['id']}/export", params={"format": "csv", "state": "accepted"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "LeadRank score" in resp.text
    assert resp.text.count("\n") >= 1  # header + at least one accepted row

    hubspot = client.get(f"/api/v1/runs/{run['id']}/export", params={"format": "hubspot", "state": "accepted"})
    assert hubspot.status_code == 200
    assert "Company domain name" in hubspot.text


def test_suppression_lifecycle(client):
    domain = "suppressme-example.com"

    resp = client.post("/api/v1/suppression", params={"domain": domain, "reason": "do-not-contact"})
    assert resp.status_code == 200
    assert resp.json()["suppressed"] is True

    listed = client.get("/api/v1/suppression").json()
    assert any(e["domain"] == domain for e in listed)

    resp = client.delete(f"/api/v1/suppression/{domain}")
    assert resp.status_code == 200
    assert resp.json()["suppressed"] is False

    listed_after = client.get("/api/v1/suppression").json()
    assert not any(e["domain"] == domain for e in listed_after)


def test_search_run_requires_saasquatch_api_key(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "saasquatch_api_key", "")
    resp = client.post("/api/v1/runs/search", json={"profile_id": SELL_PROFILE_ID, "industry": "hvac"})
    assert resp.status_code == 400
    assert "LEADRANK_SAASQUATCH_API_KEY" in resp.json()["detail"]


def test_search_run_wires_saasquatch_source_through_same_pipeline(client, monkeypatch):
    """SaaSquatchSource is a real seam, not a stub: mocking only its network
    call (fetch) and asserting the run still comes out fully deduped, scanned
    and scored proves the pipeline itself is source-agnostic."""
    from app.core.sources import SaaSquatchSource

    async def fake_fetch(self, **params):
        assert params["industry"] == "hvac"
        return [
            {
                "company_name": "Searchtime HVAC",
                "normalized_name": "searchtime hvac",
                "domain": "searchtimehvac.com",
                "normalized_domain": "searchtimehvac.com",
                "country": "United States",
                "city": "Denver",
                "industry": "hvac",
                "employee_count": 30,
                "revenue_estimate": 5_000_000.0,
                "owner_name": "Pat Owner",
                "email": "pat@searchtimehvac.com",
                "email_status": "unknown",
                "phone": "+15125550199",
                "linkedin_url": None,
                "passthrough": {},
                "provenance": {"domain": {"source": "saasquatch"}},
                "merged_from": [],
            },
        ]

    monkeypatch.setattr(SaaSquatchSource, "fetch", fake_fetch)

    resp = client.post(
        "/api/v1/runs/search",
        json={"profile_id": SELL_PROFILE_ID, "industry": "hvac", "limit": 10},
    )
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["id"]

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "complete", run
    assert run["row_count"] == 1
    assert run["stats"]["source"] == "saasquatch"

    leads = client.get(f"/api/v1/runs/{run_id}/leads").json()
    assert leads["total"] == 1
    lead = leads["items"][0]
    assert lead["company_name"] == "Searchtime HVAC"
    assert lead["band"] in {"A", "B", "C", "D"}


def test_learning_is_gated_on_sample_size(client):
    run = _create_run(client)
    # Only 3 leads in this run — well under learning_min_decisions (15) — so
    # the endpoint must decline rather than propose noisy weights.
    resp = client.get(f"/api/v1/runs/{run['id']}/learning")
    assert resp.status_code == 200
    body = resp.json()
    assert body["eligible"] is False
    assert body["proposals"] == []
