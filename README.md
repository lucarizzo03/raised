# Raised

Finds recently funded startups that look ready to build a sales team, and ranks
them for outreach.

**[Open the dashboard →](https://raised-lac.vercel.app)**

> **Claude extracts. Jev judges. Python scores. Supabase stores. Next.js displays.**

- [How it works](#how-it-works)
- [What Jev decides](#what-jev-decides)
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

1. **Check** — confirm the Claude and Jev accounts work before touching anything.
2. **Discover** — pull the last 3 days of TechCrunch RSS, Google News and SEC Form D filings, skipping articles already processed on an earlier day.
3. **Extract** — Claude Sonnet 4.5 pulls the company, round, amount and date out of each article.
4. **Verify** — confirm the company's domain, drop duplicates and reject stale or unverifiable rounds.
5. **Enrich & judge** — check job boards (Ashby, Greenhouse, Lever) and about pages; Jev makes the calls listed [below](#what-jev-decides).
6. **Score & store** — Python adds up points and saves everything to Postgres.

### Who does what

| Step | Handled by |
|---|---|
| Funding extraction | Claude Sonnet 4.5 (`claude-sonnet-4-5`) |
| Every judgment call ([list](#what-jev-decides)) | TypeSafe Jev, always (the run stops if Jev is unavailable) |
| Scoring and explanations | Plain Python — no model |
| Email drafts | Fixed TypeScript template — no model |

**Stack:** Python 3.12 · Anthropic SDK · TypeSafe Jev · Supabase Postgres ·
Next.js 16 · React 19 · Tailwind 4 · Vercel · GitHub Actions

---

## What Jev decides

Jev answers every judgment question in the pipeline. Claude only reads articles;
Python only applies rules to Jev's answers. Each answer comes with a confidence,
and anything under **0.7** (**0.4** for ICP fit, a 5-step rubric) is flagged
"needs review" on the dashboard. An "unknown" answer is missing data, not doubt,
and is never flagged.

| # | When | Jev decides | Answer | What the pipeline does with it |
|---|---|---|---|---|
| 1 | Screening | Is this article announcing a **new** round, not an old one? | yes / no | A confident "no" rejects the company (`not_new_round`) |
| 2 | Company | Is this really a company raising money (not a bar, event or product launch)? | yes / no | A confident "no" rejects it (`not_startup_raise`) |
| 3 | Company | Is it a venture-backed tech startup? | yes / no | A confident "no" rejects it (`not_startup_raise`) |
| 4 | Company | Who does it sell to? | B2B / B2C / Both / Unclear | Confident B2C is hidden; B2B shows in the explanation |
| 5 | Company | Which round is it? | Pre-seed … Later | Replaces Claude's label; Seed–Series B earns +15, "Later" over $200M is hidden |
| 6 | Company | How well does it fit the ideal customer? | 0–4 | 0–20 points |
| 7 | Each sales-looking job | Is this a sales role? | yes / no | Any "yes" earns +15; the titles show on the dashboard |
| 8 | Each sales-looking job | What kind? | AE / SDR / Head of Sales / Other | Shown on the dashboard only |
| 9 | About page | Are the founders technical? | yes / no / unknown | +10 for yes; "unknown" (page doesn't name the founders) scores nothing and shows "Founders: unknown" |
| 10 | About page | Is this their first sales hire? | yes / no | +30, only if #7 also found an open sales role |
| 11 | Investigation | Enough evidence, or dig further? | score now / check careers / search news / fetch about page | Gathers that evidence and re-asks #2–#6; at most 3 rounds |

**Jev doesn't decide:** what an article says (Claude), whether a domain is
real, dates and freshness, duplicates, or the point values and cut-offs (all
plain Python). The #2–#3 rejections are skipped if they would hit most of a
day's batch, which points to a model problem rather than bad companies.

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
  `DATABASE_URL`, and the variable `EDGAR_USER_AGENT`.
  - `DATABASE_URL` must be Supabase's **Session pooler** URL: GitHub runners
    can't reach the direct database host, which is IPv6-only.
  - If Claude or Jev runs out of funds, the run stops before saving anything and
    picks up again once funds are added. Failures don't open GitHub issues.

Details: [docs/operations.md](docs/operations.md#deployment).

---

## More docs

- [How it works](docs/how-it-works.md): the pipeline, models, date rules, scoring and database
- [Operations](docs/operations.md): deployment, testing and known limitations
