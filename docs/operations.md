# Operating Raised

Setup gotchas, deployment, testing and known limitations.
For an overview, see the [README](../README.md).

- [Setup notes](#setup-notes)
- [Deployment](#deployment)
- [Testing](#testing)
- [Security](#security)
- [Known limitations](#known-limitations)

---

## Setup notes

- **`migrate` needs the base tables.** Run `schema.sql` first on a new database.
  `run` and `cleanup` also apply migrations automatically.
- **Using `psql`?** Export `DATABASE_URL` in your shell first — dotenv doesn't.
- **Legacy rows** without publication dates stay hidden until `cleanup`
  validates or quarantines them.
- **Backfill runs once.** Completion is recorded in `pipeline_settings` and
  repeats are refused. A run that crashes before saving doesn't use it up. Never
  schedule it.
- **`cleanup` is not a preview.** It calls models and changes stored data.
  Diagnostic commands (`discover`, `jobs`, `judge`, `score`) don't write to the
  database but can still cost API usage.
- **`--mock-models`** stubs extraction and judgments. It's rejected for `run` and
  `cleanup`, and doesn't stop database reads or job-board requests.
- **`run_pipeline` and `python -m src.main`** are the same entry point.
- **Dependencies are hash-pinned.** Edit `pipeline/requirements.in`, then
  regenerate `requirements.txt` with the command at the top of that file.
  Install with `pip install --require-hashes -r requirements.txt`.
- **Migrations** live in `pipeline/migrations/` and all run, in order, on
  `migrate`, `run` and `cleanup`. Each file must be safe to re-run.
- **Dashboard env vars** (`SUPABASE_URL`, `SUPABASE_ANON_KEY`) are server-only —
  no `NEXT_PUBLIC_` prefix. The dashboard needs no model keys.
- **No auth.** The schema grants anonymous read access; there's no sign-in.

---

## Deployment

### Vercel (dashboard)

- Root directory: **`dashboard/`**, framework: Next.js.
- Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` for **Production** (and **Preview**
  if previews should hit a database).
- If either variable is missing or a query fails, the page shows
  **Sample data**. An empty result is a real (empty) ranking. Check Vercel
  server logs for query errors.
- Local commits don't deploy — push to the connected branch.

### GitHub Actions (pipeline)

[`daily.yml`](../.github/workflows/daily.yml) runs at **13:00 UTC** (8 AM EST /
9 AM EDT) and can be triggered manually. GitHub may delay scheduled runs.

| Type | Name |
|---|---|
| Secret | `ANTHROPIC_API_KEY` |
| Secret | `TYPESAFE_API_KEY` |
| Secret | `DATABASE_URL` |
| Variable | `EDGAR_USER_AGENT` (real SEC contact) |
| Variable | `JUDGE_BACKEND` (normally `jev`) |

- The job installs hash-pinned dependencies, runs unit tests, then
  `python -m src.main run -v`. It never backfills.
- It times out after 60 minutes and never overlaps with another run.
- **A failed run opens a "Daily pipeline failing" issue** (or comments on the
  open one). Close it once the run is healthy again.
- **Failure handling:** model calls retry rate limits, overloads and timeouts
  with backoff. A company that still fails is skipped for that run and picked
  up again the next day. If more than 25% of a stage fails, the provider is
  treated as down and the run aborts **before writing anything**.
- `ANTHROPIC_MODEL` isn't passed, so the code default is used.
- Schedules run on the **default branch** — merge there to change daily behavior.

[`pipeline.yml`](../.github/workflows/pipeline.yml) runs on pipeline changes
(PRs and `main`): ruff, unit tests, database tests against a Postgres service,
and a check that the anon role can't write.

[`dashboard.yml`](../.github/workflows/dashboard.yml) type-checks, runs
`npm audit`, and runs regression tests on
pushes to `main` and on PRs, then checks the live site after production
deploys. That live check requires real logos and can fail when an external
favicon is down, even if the initials fallback works.

---

## Testing

### Pipeline (from `pipeline/`)

```bash
# Unit tests, ignoring local credentials
PYTHON_DOTENV_DISABLED=1 ../.venv/bin/python -B -m unittest discover -s tests -v

# Lint
ruff check .

# Also run database tests (uses temp tables and rolls back — prefer a test DB)
RUN_DATABASE_TESTS=1 ../.venv/bin/python -B -m unittest discover -s tests -v
```

### Dashboard (from `dashboard/`)

```bash
npx tsc --noEmit --incremental false
npm run build
npx playwright install chromium
npm test
```

`npm test` starts an isolated production server on **port 3100** with sample
data (keep the port free). It covers table interactions, responsive layout,
image fallbacks, the logo endpoint and security headers (including no
Content-Security-Policy violations).

Against the live site:

```bash
PLAYWRIGHT_BASE_URL=https://raised-lac.vercel.app npm test

# Skip strict logo checks
PLAYWRIGHT_BASE_URL=https://raised-lac.vercel.app npm test -- dashboard.spec.ts
```

Protected Vercel previews may need authentication.

---

## Security

- **Database:** the anon key can only `select` from `companies`, `signals`,
  `scores`, `decisions` and `ranked_companies`. `rejected_companies` and
  `pipeline_settings` are closed to it entirely (migration 002).
- **Fetching:** the pipeline only fetches http(s) URLs, refuses private,
  loopback and link-local addresses (including cloud metadata endpoints) on
  every redirect hop, and drops responses over 5 MB.
- **Dashboard:** sends CSP, `X-Frame-Options`, `nosniff`, referrer and HSTS
  headers. The logo endpoint validates domains and only follows Google's
  image redirects.
- **CI:** actions are pinned to commit SHAs, workflows default to read-only
  tokens, and checkout doesn't persist credentials.

---

## Known limitations

- **Known companies aren't refreshed daily.** Deduped companies (including
  excluded ones) are skipped, so their hiring signals and recency points aren't
  recomputed. Date-based hiding and age-out still apply.
- **Source coverage is limited.** RSS feeds are short, EDGAR reads one results
  page, and some publishers block fetching.
- **Judgments aren't verified facts.** Job-board slug matching and first-hire
  detection are heuristics — check sources before outreach.
- **CLI and dashboard rankings differ.** `ranked` shows the newest score batch
  without the view's filters; the dashboard shows each company's latest score
  with filters. The UI labels unknown rounds as `Later`.
- **Scores can reach 120**, but the score bar caps at 100.
- **Heartbeat starts after the first run with this code.** Until then, the
  header falls back to the latest signal timestamp. After it, "Updated" means
  the last successful run, and it turns amber ("pipeline may be stalled") after
  36 hours.
- **The [freshness audit](../pipeline/reports/freshness_audit.json)** is a dated
  snapshot, not a live count.
