# Operating Raised

Setup gotchas, deployment, testing and known limitations.
For an overview, see the [README](../README.md).

- [Setup notes](#setup-notes)
- [Deployment](#deployment)
- [Testing](#testing)
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

- The job installs dependencies, runs unit tests, then `python -m src.main run -v`.
  It never backfills.
- `ANTHROPIC_MODEL` isn't passed, so the code default is used.
- Schedules run on the **default branch** — merge there to change daily behavior.

[`dashboard.yml`](../.github/workflows/dashboard.yml) runs regression tests on
pushes to `main` and on PRs, then checks the live site after production
deploys. That live check requires real logos and can fail when an external
favicon is down, even if the initials fallback works.

---

## Testing

### Pipeline (from `pipeline/`)

```bash
# Unit tests, ignoring local credentials
PYTHON_DOTENV_DISABLED=1 ../.venv/bin/python -B -m unittest discover -s tests -v

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
image fallbacks and the logo endpoint.

Against the live site:

```bash
PLAYWRIGHT_BASE_URL=https://raised-lac.vercel.app npm test

# Skip strict logo checks
PLAYWRIGHT_BASE_URL=https://raised-lac.vercel.app npm test -- dashboard.spec.ts
```

Protected Vercel previews may need authentication.

---

## Known limitations

- **Known companies aren't refreshed daily.** Deduped companies (including
  excluded ones) are skipped, so their hiring signals and recency points aren't
  recomputed. Date-based hiding and age-out still apply.
- **Source coverage is limited.** RSS feeds are short, EDGAR reads one results
  page, and some publishers block fetching.
- **Some judgments don't filter.** Negative `genuine_raise` and `is_startup`
  answers are recorded but don't remove a company.
- **Judgments aren't verified facts.** Job-board slug matching and first-hire
  detection are heuristics — check sources before outreach.
- **CLI and dashboard rankings differ.** `ranked` shows the newest score batch
  without the view's filters; the dashboard shows each company's latest score
  with filters. The UI labels unknown rounds as `Later`.
- **Scores can reach 120**, but the score bar caps at 100.
- **"Updated" isn't a cron heartbeat.** It's the latest signal timestamp. Check
  Actions logs for run health.
- **The [freshness audit](../pipeline/reports/freshness_audit.json)** is a dated
  snapshot, not a live count.
