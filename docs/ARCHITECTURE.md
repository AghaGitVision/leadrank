# Architecture

This document covers UX/backend design choices, data storage, caching, hosting,
deployment, and cloud provider — as the challenge brief asks for explicitly.

## Summary

| Layer | Local / demo | Production target |
|---|---|---|
| Frontend | Next.js dev server | **Vercel** — static shell + edge routes |
| API | Uvicorn, single process | **Google Cloud Run** — serverless containers |
| Database | SQLite file | **PostgreSQL** (Neon or Cloud SQL) |
| Cache / queue | In-process dict | **Redis** (Upstash) |
| File storage | Local disk (not used in v1 — CSV is streamed in-memory) | **GCS** with signed URLs |
| CI/CD | — | GitHub Actions → Cloud Run + Vercel |

Every production dependency sits behind an interface that already has a local,
zero-infrastructure implementation (`app/core/cache.py`, `app/db.py`). Setting
`LEADRANK_DATABASE_URL` or `LEADRANK_REDIS_URL` is what switches it — there is
no code fork between "demo mode" and "production mode."

## Why this stack

**Cloud Run over a persistent server.** The workload is bursty by nature — a
user uploads a list, the system does a burst of scanning and scoring, then sits
idle until the next upload. Cloud Run scales to zero between runs and bills
per request, which fits that shape far better than a server that's paid for
24/7 to sit idle most of the time. It also means the container that runs in
production is the exact container tested locally via `docker-compose`.

**Vercel for the frontend.** Next.js is a first-class target; the marketing
site pattern (mostly static, a few dynamic routes) matches the app's actual
shape — setup and triage are the only two screens.

**Postgres over a document store.** The lead record has real structure and the
one query that matters — "give me this run's leads sorted by score, filtered
by band" — is a straightforward indexed range scan. JSONB columns hold the
genuinely unstructured parts (`weights`, `targeting`, `scan_payload`) without
giving up relational integrity on the columns that need it. A `B-tree` index
on `(run_id, score DESC)` is the hot path and it's a one-line index in
Postgres.

**Redis for the scan cache, not the database.** A scan payload is disposable —
losing it just means one extra fetch, not data loss — so it belongs in a cache
with a TTL, not in the system of record. Upstash's HTTP-based Redis fits
serverless functions that don't hold a persistent connection.

## Data model

See `app/models.py` for the SQLAlchemy definitions. The design decisions worth
calling out:

- **`lead_signals` is one row per evaluated signal**, not a JSON blob on the
  lead. This is what makes the explanation view (`GET /leads/{id}/explain`) a
  query instead of a recomputation, and what makes every point of every score
  auditable after the fact — including for leads whose scan payload has since
  expired from cache.
- **`scan_payload` on the lead is a snapshot; `scan_snapshots` is history.**
  The lead always shows its current signals. The snapshot table is what
  `diff_snapshots()` compares against on a rescan, which is what turns a
  static export into a watchlist.
- **`decisions` is an append-only log of accept/reject events**, separate from
  `review_state` on the lead. The lead's state can change (undo, re-review);
  the decision log cannot, because it's the training signal for
  `learn_weights()`.
- **Every mergeable field carries provenance** (`{source, column}` or
  `{source: "scan"}`). When two duplicate rows are merged, the surviving value
  keeps a record of where it came from, which is what makes a merge auditable
  rather than a silent overwrite.

## Scoring is decoupled from scanning and from the database

`app/core/scoring.py` takes a `Features` object and a weights dict and returns
a `ScoreResult`. It never touches the database, the network, or a request
object. This is deliberate for three reasons:

1. **Testability.** The 22 tests in `tests/test_core.py` construct a
   `Features` object by hand and assert on exact numbers — no fixtures,
   no mocking, no network.
2. **Rescoring without refetching.** `POST /runs/{id}/rescore` replays the
   *cached* scan payload already on each lead through new weights. No network
   call happens. This is what makes live weight-tuning viable in the demo —
   tuning a slider and re-scoring 250 leads is sub-second.
3. **The learning loop proposes, it never mutates in place.** `learn_weights()`
   is a pure function over a list of `(decision, dimension_scores)` tuples. It
   returns a proposal; `POST /learning/apply` materializes that proposal as a
   *new* `ScoringProfile` row. The profile someone is actively using never
   changes underneath them.

## The scanner is a fetch, not a crawl

Bounded on purpose: at most 3 requests per domain (home page + up to 2 of
`/about`, `/contact`, `/careers`), a 5-second timeout, `robots.txt` checked and
respected before every request, an identifying user agent, and a global
concurrency semaphore plus a per-host limit of one in-flight request. Every
signal extracted from the HTML is regex or parser based (`selectolax` for DOM,
plain regex for copyright years, tech fingerprints, and copy markers) — no
model is involved in producing a signal, because signals feed the score and
the score has to be reproducible.

The scanner has two modes, selected by `LEADRANK_SCAN_MODE`:

- `offline` (default) replays bundled fixtures from
  `app/data/scan_fixtures.json`. The demo and the test suite run with zero
  egress and zero flakiness from real-world site availability.
- `live` performs the actual HTTP fetch described above.

A payload is tagged `"fixture": true` in offline mode so nothing is ever
presented as a live result when it wasn't.

## Caching

`ScanCache` (`app/core/cache.py`) wraps either Redis or an in-process dict
behind one interface. Key shape: `scan:{sha256(domain)}`. Value: the *parsed
signal envelope*, not raw HTML — roughly 1KB instead of ~200KB, and directly
replayable by the rescoring path. TTL is 7 days by default
(`LEADRANK_SCAN_CACHE_TTL_DAYS`). Cache hit rate is tracked and surfaced in
`run.stats.scan_cache_hit_rate` — the number to point at in the demo is that a
second run over an overlapping list is close to instant, because it's a cache
read, not a re-fetch.

## API surface

Full route list in `app/api/`. The four worth explaining:

- **`POST /runs/search`** takes the same `LeadSource` protocol `POST /runs`
  does, but backs it with `SaaSquatchSource` instead of `CsvSource` — search
  parameters in, a `Run` scored through the identical dedupe/scan/score
  pipeline out. Gated on `LEADRANK_SAASQUATCH_API_KEY`: unset, it returns 400
  instead of a silent no-op. `tests/test_api.py` proves the pipeline wiring
  with a mocked `fetch()`, since no live key ships with this submission.
- **`GET /runs/{id}/events`** is a Server-Sent Events stream, not a polling
  endpoint. The client keeps one open connection while a run is scanning;
  the server pushes progress on any state change. Chosen over WebSockets
  because it's one-directional, works over plain HTTP, and needs no extra
  infrastructure on either Cloud Run or Vercel.
- **`POST /runs/{id}/rescore`** accepts either a `profile_id` or an inline
  `weights` override. An inline override creates an *ephemeral* profile object
  for that one request — it is not persisted unless the user separately saves
  it via `POST /profiles`. This is what backs the "adjust weights, see the
  queue reshuffle, decide whether to keep it" interaction.
- **`POST /runs/{id}/rescan`** re-fetches each lead's domain, diffs the new
  scan against the last stored snapshot, and writes any detected changes as
  `Alert` rows. This is the mechanism behind the "what changed" panel in the
  UI and is what turns a one-time export into something worth holding onto.

## CI/CD

`.github/workflows/ci.yml` runs on every push and PR to `main`, as three
independent jobs so a frontend failure never blocks a backend result and
vice versa:

```
push / PR to main
  → GitHub Actions
    ├─ backend-tests   : pip install -r requirements.txt → pytest tests/ -v
    ├─ frontend-build  : npm ci → eslint . → next build (type-check included)
    └─ commitlint      : commitlint --from <base> --to HEAD (Conventional Commits)
```

Not yet wired: a Python lint gate (no `ruff` job today — only pytest runs on
the backend), and the deploy half of the pipeline — build & push container →
Cloud Run deploy, and a Vercel deploy via its GitHub integration. Those are
the next two jobs to add, gated behind the three above passing, once a real
target environment exists to deploy to.

## Observability

Structured JSON logs (see `app/main.py`'s logging config) are the baseline;
production would add Sentry for exception tracking. The per-run `stats` blob
(`bands`, `quadrants`, `scan_statuses`, `scan_cache_hit_rate`, `alerts`) is
already computed and stored on every run — in production this is also the
payload a dashboard would read from, rather than needing a separate metrics
pipeline for run-level numbers.

## What would change first at real scale

- **Background jobs move off `BackgroundTasks`** (FastAPI's in-process task
  runner, used here for simplicity) **onto ARQ backed by Redis.** Cloud Run
  instances are ephemeral and can be recycled mid-request; a run in progress
  during a scale-down event would be lost with `BackgroundTasks`. ARQ jobs
  survive because they're queued in Redis, not held in a process's memory.
- **The scanner's per-host limit becomes a distributed rate limiter** (a
  Redis-backed token bucket) once scanning runs across more than one Cloud Run
  instance concurrently — the current in-process semaphore only coordinates
  within a single instance.
- **`lead_signals` gets partitioned or archived past a retention window** —
  it's the fastest-growing table (roughly 9 rows per lead per scoring mode)
  and old runs' signal rows are rarely queried once a run is stale.
