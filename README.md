# Raised

Daily pipeline that finds early-stage startups that just raised money and are
starting to hire sales, then scores and ranks them. Output: the ~25 companies
most worth selling to this week, and why.

**Architecture: LLM extracts, Jev judges, plain code scores.**

## Layout

```
pipeline/     Python pipeline (httpx + asyncio)
dashboard/    Next.js + TypeScript + Tailwind, deploys to Vercel
.github/      Daily GitHub Actions cron
```

## The Jev / LLM / code split

| Step | Runs on | Why |
|---|---|---|
| Feed fetch, HTML→text, dedupe, job-board probing | code | deterministic, no judgment needed |
| Article → funding event (name, domain, round, amount, date, investors) | LLM | unstructured text → structured fields; returns `not_funding_article` instead of guessing |
| Is genuine raise? Which round? ICP fit? Is sales role? Role type? Founders technical? First sales hire? Score-now-or-dig-deeper? | Jev (`TypeSafeClassifier`) | typed judgments with confidence; cheap and fast |
| Scoring, ranking, explanation text | code | weights in one config block; never calls a model |

Every Jev call sits behind `Judge` (`pipeline/src/judge.py`) with a regular LLM
+ structured JSON output as the fallback. `JUDGE_BACKEND=jev|llm` toggles it;
default is `jev` when `TYPESAFE_API_KEY` is set. Any answer under 0.7
confidence is flagged `needs_review`. Jev only ever sees extracted fields —
never raw articles.

## Scoring weights

All weights live in `SCORING_WEIGHTS` in `pipeline/src/config.py`:

| Rule | Points |
|---|---|
| Raised within 30 days | +30 |
| Raised 31–90 days ago | +15 |
| Round is Seed–Series B | +15 |
| First sales hire | +30 |
| Any sales role open | +15 |
| Technical founders | +10 |

Sum, sort descending, record which rules fired per company.

## Data sources

- **Funding news**: TechCrunch RSS, Google News RSS (`raises Seed` /
  `Series A` / `Series B`, 30d window, redirect URLs decoded via
  `googlenewsdecoder`), SEC EDGAR full-text search (Form D).
- **Job boards**: public JSON APIs for Ashby, Greenhouse, Lever. Slug guessed
  from the domain; first board that responds wins.
- **Company pages**: plain HTTP fetch of `/about`, `/team`, `/careers`, `/jobs`.

## Investigation loop

After initial judgments, Jev answers "score now or dig deeper?" per company.
If it digs, it picks exactly one action — `check_careers`, `search_news`, or
`fetch_about` — the evidence is gathered, and the company is re-judged. Max 3
rounds; every decision is logged to the `decisions` table and shown in the
dashboard row expansion.

## Data model

- `companies` — name, domain (unique), round, amount_raised, raised_date, first_seen
- `signals` — typed judgments w/ confidence, needs_review flag, source_url
- `scores` — one row per company per run: score, explanation, rules_fired
- `decisions` — investigation-loop audit trail
- `ranked_companies` (view) — latest run's ranking for the dashboard

## Setup

### Pipeline

```bash
cd pipeline
python3.12 -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in keys
```

Env vars: `ANTHROPIC_API_KEY` (extraction + judge fallback — Anthropic
only), `TYPESAFE_API_KEY` (Jev), `DATABASE_URL` (Supabase Postgres
connection string), optional `ANTHROPIC_MODEL`, `JUDGE_BACKEND`,
`EDGAR_USER_AGENT`.

Create the schema by running `schema.sql` in the Supabase SQL editor or
`psql "$DATABASE_URL" -f schema.sql`.

### Commands (phase-gated)

```bash
../.venv/bin/python -m src.main discover   # feeds -> extract -> dedupe
../.venv/bin/python -m src.main jobs       # + job boards
../.venv/bin/python -m src.main judge      # + Jev judgments w/ confidence
../.venv/bin/python -m src.main score      # + investigation loop + ranking
../.venv/bin/python -m src.main run        # everything + persist to Postgres
../.venv/bin/python -m src.main ranked     # print latest ranking from DB
```

`--mock-models` stubs extraction/judgments to verify plumbing without keys.

### Dashboard

```bash
cd dashboard
npm install
cp .env.local.example .env.local  # NEXT_PUBLIC_SUPABASE_URL + ANON_KEY
npm run dev
```

Deploys to Vercel; set the same env vars there. Reads the `ranked_companies`
view plus `signals`/`decisions` via the Supabase anon key (RLS read policies
in `schema.sql`). Without env vars it renders bundled sample data.

### Cron

`.github/workflows/daily.yml` runs `python -m src.main run` daily at 13:00
UTC. Required secrets: `ANTHROPIC_API_KEY`, `TYPESAFE_API_KEY`,
`DATABASE_URL`.
