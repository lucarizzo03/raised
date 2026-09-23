# Raised

Finds recently funded startups that look ready to build a sales team, and ranks
them for outreach.

**[Open the dashboard →](https://raised-lac.vercel.app)**

> **Claude extracts. Jev judges. Python scores. Supabase stores. Next.js displays.**

- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Scoring](#scoring)
- [Testing](#testing)
- [Deployment](#deployment)
- [More docs](#more-docs)

---

## How it works

A Python pipeline runs daily on **GitHub Actions** and writes to **Supabase**.
The **Next.js** dashboard on **Vercel** only reads that data — opening the site
never runs the pipeline or calls a model.

```mermaid
flowchart LR
    A["News + SEC filings"] --> B["Claude<br/>extract funding round"]
    B --> C["Python<br/>verify domain, dedupe,<br/>date checks"]
    C --> D["Jev<br/>judge company, jobs,<br/>founders"]
    D --> E["Python<br/>score"]
    E --> F[("Supabase")]
    F --> G["Dashboard"]
```

1. **Discover** — pull the last 3 days of TechCrunch RSS, Google News and SEC Form D filings.
2. **Extract** — Claude Sonnet 4.5 pulls the company, round, amount and date out of each article.
3. **Verify** — confirm the company's domain, drop duplicates and reject stale or unverifiable rounds.
4. **Enrich & judge** — check job boards (Ashby, Greenhouse, Lever) and about pages; Jev decides whether they're hiring sales, B2B, technical founders, etc.
5. **Score & store** — Python adds up points and saves everything to Postgres.

### Who does what

| Step | Handled by |
|---|---|
| Funding extraction | Claude Sonnet 4.5 (`claude-sonnet-4-5`) |
| Company, job and founder judgments | TypeSafe Jev (falls back to Claude if Jev can't start) |
| Scoring and explanations | Plain Python — no model |
| Email drafts | Fixed TypeScript template — no model |

**Stack:** Python 3.12 · Anthropic SDK · TypeSafe Jev · Supabase Postgres ·
Next.js 16 · React 19 · Tailwind 4 · Vercel · GitHub Actions

---

## Quick start

**You need:** Python 3.12, Node.js 22+, a Supabase project, an Anthropic API key
and a TypeSafe API key.

### 1. Pipeline

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r pipeline/requirements.txt
cp -n pipeline/.env.example pipeline/.env   # then fill it in
```

| Variable | Required | Purpose |
|---|:---:|---|
| `DATABASE_URL` | ✓ | Postgres connection (needs write access) |
| `ANTHROPIC_API_KEY` | ✓ | Claude extraction |
| `TYPESAFE_API_KEY` | ✓ | Jev judgments |
| `EDGAR_USER_AGENT` | ✓ | Your app name + contact email, required by the SEC |
| `ANTHROPIC_MODEL` | | Override the Claude model |
| `JUDGE_BACKEND` | | `jev` or `llm` |

### 2. Database

For a **new** database, run [`pipeline/schema.sql`](pipeline/schema.sql) in the
Supabase SQL editor, then:

```bash
cd pipeline
../.venv/bin/python run_pipeline migrate
../.venv/bin/python run_pipeline --backfill   # one-time 30-day seed
```

For an **existing** database, just run `migrate` (never re-run the schema).

### 3. Dashboard

From the repo root:

```bash
cd dashboard
npm ci
cp -n .env.local.example .env.local   # set SUPABASE_URL and SUPABASE_ANON_KEY
npm run dev
```

Without Supabase credentials, the dashboard shows bundled **sample data**.

---

## Commands

Run from `pipeline/` as `../.venv/bin/python run_pipeline <command>`.

| Command | What it does | Writes to DB? |
|---|---|:---:|
| `run` *(default)* | Full daily pipeline | ✓ |
| `--backfill` | Full pipeline with a 30-day lookback — **run once only** | ✓ |
| `cleanup` | Re-check stored companies' dates and sources (calls models) | ✓ |
| `migrate` | Apply schema migrations and settings | ✓ |
| `discover` | Stop after extraction and dedupe; print candidates | |
| `jobs` | …plus date screening and job boards | |
| `judge` | …plus Jev judgments | |
| `score` | …plus scoring; print the ranking | |
| `ranked` | Print the latest score batch | |

Flags: `-v` for verbose logs · `--mock-models` to skip model calls
(diagnostic commands only, e.g. `discover --mock-models`).

---

## Scoring

Points are additive (max **120**) — not a percentage.

| Signal | Points |
|---|---:|
| Raise recency (fades to 0 over 90 days) | 0–30 |
| Seed, Series A or Series B | +15 |
| Open sales role | +15 |
| …and it's their first sales hire | +30 more |
| Technical founder | +10 |
| ICP fit | 0–20 |

Automatically hidden: confident B2C companies, late-stage companies with more
than $200M raised, and anything whose raise is older than 90 days. Hidden
companies are kept in the database, never deleted.

Weights live in [`pipeline/src/config.py`](pipeline/src/config.py).

---

## Testing

```bash
# Pipeline (from pipeline/)
PYTHON_DOTENV_DISABLED=1 ../.venv/bin/python -B -m unittest discover -s tests -v

# Dashboard (from dashboard/)
npx playwright install chromium
npm test
```

`npm test` starts a production build on **port 3100** using sample data.
See [docs/operations.md](docs/operations.md#testing) for database tests and
checking the live site.

---

## Deployment

- **Dashboard** → Vercel, with root directory `dashboard/` and `SUPABASE_URL` +
  `SUPABASE_ANON_KEY` set.
- **Pipeline** → [GitHub Actions](.github/workflows/daily.yml), daily at
  **13:00 UTC**. Needs secrets `ANTHROPIC_API_KEY`, `TYPESAFE_API_KEY` and
  `DATABASE_URL`, and variables `EDGAR_USER_AGENT` and `JUDGE_BACKEND`.

Details: [docs/operations.md](docs/operations.md#deployment).

---

## More docs

| Doc | Covers |
|---|---|
| [docs/how-it-works.md](docs/how-it-works.md) | Pipeline stages, model behavior, date windows, rejection rules, scoring formulas, database tables |
| [docs/operations.md](docs/operations.md) | Setup gotchas, deployment, testing, known limitations |

```text
pipeline/    Python pipeline, schema, migrations and tests
dashboard/   Next.js dashboard and Playwright tests
.github/     Daily pipeline and dashboard CI workflows
docs/        Detailed reference
```
