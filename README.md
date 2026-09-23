# Raised

Finds recently funded startups that look ready to build a sales team, and ranks
them for outreach.

**[Open the dashboard →](https://raised-lac.vercel.app)**

> **Claude extracts. Jev judges. Python scores. Supabase stores. Next.js displays.**

- [How it works](#how-it-works)
- [Scoring](#scoring)
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
than $200M raised, records that clearly aren't a startup raising money, and
anything whose raise is older than 90 days. Hidden companies are kept in the
database, never deleted.

Weights live in [`pipeline/src/config.py`](pipeline/src/config.py).

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

- [How it works](docs/how-it-works.md): the pipeline, models, date rules, scoring and database
- [Operations](docs/operations.md): deployment, testing and known limitations
