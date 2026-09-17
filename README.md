# LeadRank

**A qualification layer for scraped lead lists.** Turn a CSV export into a
ranked, explained, decision-ready shortlist — before you spend a credit
enriching a company that was never a fit.

Built for the Caprae Capital AI-Readiness Challenge, against
[SaaSquatch Leads](https://www.saasquatchleads.com/).

## Why this, and not a bigger scraper

SaaSquatch already scrapes well. What it doesn't do is tell you which of the
500 rows you just pulled are worth a credit — its own product page says
"one credit unlocks the full lead profile (including Email and Phone
Number)," so every row looks identical until you've already paid for it. And
a list is not a pipeline: a rep or a searcher can act on maybe 20 companies
this week, and nothing in the export tells them which 20.

LeadRank sits between "scraped" and "contacted." It scores each company
deterministically, shows exactly why it scored that way, and — because
SaaSquatch's own site names both audiences directly ("2,000+ sales teams"
and "30+ Entrepreneurs and Searchers" use the product today, per
saasquatchleads.com) — it does this in two modes over one engine:

- **Sell mode** — is this a customer worth reaching?
- **Buy mode** — is this a business worth acquiring?

The same signal flips sign between the two. A dated website with no analytics
disqualifies a sales lead and *is the thesis* for an acquisition target: a
good business nobody has modernized yet. That inversion — not a bigger
scraper — is the core idea. See `docs/ARCHITECTURE.md` for the technical
writeup and the spec's §4 for the full scoring design.

## What's in this build

| Area | What it does |
|---|---|
| **Ingestion** | CSV upload with auto-detected column mapping, shown to the user for confirmation before anything is scored |
| **Data quality** | Normalization (domains, phones, revenue in any format, names), exact + fuzzy dedupe with provenance-aware merging, four-state email validation (valid/risky/unknown/invalid — role accounts are `risky`, not thrown out) |
| **Signal scanner** | One polite HTTP pass per domain — robots.txt respected, rate limited, ≤3 requests per host — extracting tech stack, contact info, freshness, and copy markers. Ships with an **offline fixture mode** so the demo and CI run with zero network access |
| **Scoring engine** | Deterministic, additive, fully inspectable. Score and confidence are separate axes — never multiplied together — which produces a "spend a credit here" quadrant that maps directly onto SaaSquatch's own revenue model |
| **Explanation** | Every score has a signal-by-signal waterfall: what it gained, what it left on the table, and what was never observed at all |
| **Triage workspace** | A ranked queue with full keyboard review (`J`/`K` move, `A` accept, `X` reject, `E` enrich, `U` undo) — reviewing 50 leads without touching the mouse |
| **Export** | Accepted leads only, with score/band/confidence and the top-3 reasons as columns, mapped to HubSpot or Salesforce field names |
| **Weight learning** | Proposes new dimension weights from the user's own accept/reject decisions, gated on sample size, bounded per pass, shown as evidence — never silently applied |
| **Change monitoring** | Re-scanning a run's domains and diffing against the last snapshot surfaces exactly the events that matter: a careers page appearing (budget moved), "acquired by" copy appearing (target is gone) |
| **Source adapter seam** | `app/core/sources.py` defines `LeadSource` as a protocol with a CSV implementation and a `SaaSquatchSource` stub — the integration point for scoring at search time instead of after export |

## Quick start

### Option A — Docker (full stack, closest to production topology)

```bash
cp .env.example backend/.env
docker compose up --build
```

Frontend: http://localhost:3000 · API: http://localhost:8000/health

### Option B — run locally without Docker

**Backend:**
```bash
cd backend
pip install -r requirements.txt --break-system-packages   # or use a venv
python scripts/generate_seed.py     # regenerates the bundled demo dataset (optional — it's already committed)
uvicorn app.main:app --reload --port 8000
```

**Frontend** (separate terminal):
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000, choose **Businesses to buy** or **Customers to
sell to**, and upload `backend/app/data/seed_leads.csv` — a 322-row synthetic
dataset (with 22 deliberate duplicates and every revenue format the parser
needs to handle) built specifically to exercise dedupe, validation, and both
scoring modes end to end.

### API walkthrough (no UI needed)

With the backend running, this script drives the whole pipeline end to end —
upload, scan, score, explain, the buy/sell rescore-in-place, and export — and
prints real numbers read from the live API at each step. It's a faster way
for a reviewer to see the buy/sell inversion than clicking through the UI:

```bash
cd backend
python scripts/api_demo.py
```

### Running the tests

```bash
cd backend
python -m pytest tests/ -v
```

22 tests, no network required — they cover the scoring engine's determinism,
the buy/sell inversion, confidence-vs-score separation, dedupe merge behavior,
email validation edge cases, the scanner's HTML parsing, and the bounds on the
weight-learning loop.

## Repository layout

```
backend/
  app/
    core/            # normalize, dedupe, validate, scanner, scoring, learning,
                      # monitor, ingest, pipeline, exporter, sources, narrative
    api/              # FastAPI routers: profiles, runs, leads, insights
    data/             # bundled seed CSV + offline scan fixtures
    models.py         # SQLAlchemy schema
    schemas.py        # Pydantic request/response models
    main.py           # app entrypoint
  scripts/generate_seed.py
  scripts/api_demo.py   # end-to-end API walkthrough, no UI needed
  tests/test_core.py
frontend/
  app/                # setup screen (/) and triage workspace (/runs/[runId])
  components/Explain.tsx  # waterfall, band chip, quadrant grid
  lib/api.ts          # typed API client
docs/
  ARCHITECTURE.md      # full backend architecture writeup (data, cache, hosting, CI/CD)
  BUSINESS_ANSWERS.md  # the three required essay responses
  VIDEO_SCRIPT.md      # the 2-minute walkthrough script
```

## Rubric mapping

| Criterion | Where it shows up |
|---|---|
| **Business use case (10)** | Dual-mode design reflects that SaaSquatch serves both sellers and searchers; the score/confidence split produces exactly the "which leads justify a credit" list, which strengthens the credit-based revenue model rather than competing with it |
| **UX/UI (10)** | 30-second mode + profile setup, auto-mapped column detection, full keyboard triage, two-click export |
| **Technicality (10)** | Dedup with provenance-aware merging, four-state email validation, robots-respecting concurrent scanner, signal-level explainability, deterministic + replayable scoring, bounded weight learning from real usage |
| **Design (5)** | Native to SaaSquatch's own dark navy/cyan visual system rather than a bolted-on prototype; color reserved for band chips and the waterfall, never used as a row background |
| **Other (5)** | Ethical sourcing built in (robots.txt, rate limiting, suppression list, CAN-SPAM/GDPR export note), change monitoring turns a static export into a watchlist, honest architecture doc naming the production targets and what would change at scale |

## Ethics & data sourcing

- Public pages only. `robots.txt` is fetched and checked before every request;
  disallowed paths are recorded as `robots_disallowed`, not silently skipped.
- Business contact data only — no personal addresses, no bypassing logins or
  CAPTCHAs.
- Every field carries provenance (`{source, column}` or `{source: "scan"}`)
  and every scan is timestamped, so a user can see where a claim came from.
- A suppression list (`POST /api/v1/suppression`) removes a domain from every
  future run — used for do-not-contact lists.
- CSV export includes a compliance note on GDPR legitimate-interest and
  CAN-SPAM obligations.
- The bundled demo dataset is synthetic, generated by
  `scripts/generate_seed.py` from a fixed random seed — no real company or
  personal data is included in this repository.

## What's next (past this submission)

- Score at search time via `SaaSquatchSource`, instead of scoring a post-export
  CSV — ranking would then inform which rows are worth a credit *before* one
  is spent, not just after.
- Move background scanning off in-process `BackgroundTasks` onto an ARQ/Redis
  queue so a run survives a Cloud Run instance being recycled mid-scan.
- Scheduled rescans (not just on-demand) so the "what changed" panel becomes a
  standing watchlist rather than something triggered manually.
