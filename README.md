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
4. **Verify & screen** — confirm the company's domain, drop duplicates, reject stale or unverifiable rounds, and have Jev confirm the article announces a *new* round.
5. **Enrich & judge** — check job boards (Ashby, Greenhouse, Lever) and about pages; Jev makes the calls listed [below](#what-jev-decides).
6. **Score & store** — Python adds up points and saves everything to Postgres.

### Who does what

| Step | Handled by |
|---|---|
| Funding extraction | Claude Sonnet 4.5 (`claude-sonnet-4-5`) |
| Every judgment call ([list](#what-jev-decides)) | TypeSafe Jev. The run stops if Jev is unavailable; it never switches to Claude on its own |
| Scoring and explanations | Plain Python — no model |
| Email drafts | Fixed TypeScript template — no model |

**Stack:** Python 3.12 · Anthropic SDK · TypeSafe Jev · Supabase Postgres ·
Next.js 16 · React 19 · Tailwind 4 · Vercel · GitHub Actions

---

## What Jev decides

Jev answers every judgment question in the pipeline. Claude only reads articles;
Python only applies rules to Jev's answers. Each answer comes with a confidence,
and anything under **0.7** (**0.4** for ICP fit, **0.5** for "sells to") is flagged
"needs review" on the dashboard. An "unknown" answer is missing data, not doubt,
and is never flagged.

| # | When | Jev decides | Type | Answer | What the pipeline does with it |
|---|---|---|---|---|---|
| 1 | Screening | Is this article announcing a **new** round, not an old one? | Noul | yes / no | A confident "no" rejects the company (`not_new_round`) |
| 2 | Company | Is this really a company raising money (not a bar, event or product launch)? | Noul | yes / no | A confident "no" rejects it (`not_startup_raise`) |
| 3 | Company | Is it a venture-backed tech startup? | Noul | yes / no | A confident "no" rejects it (`not_startup_raise`) |
| 4 | Company | Who does it sell to? | Choice | B2B / B2C / Both / Unclear | Confident B2C is hidden; B2B shows in the explanation |
| 5 | Company | Which round is it? | Choice | Pre-seed / Seed / Series A / Series B / Later | Replaces Claude's label; Seed–Series B earns +15, "Later" with over $200M raised is hidden |
| 6 | Company | How well does it fit the [ideal customer](#ideal-customer-icp)? | Score | 0–4 (can be in between, e.g. 2.7) | 0–20 points |
| 7 | Each sales-looking job | Is this a direct, quota-carrying sales role? | Noul | yes / no | Any "yes" earns +15; the titles show on the dashboard |
| 8 | Each sales-looking job | What kind? | Choice | AE / SDR / Head of Sales / Other | "Other" overrides #7: the job doesn't count as sales |
| 9 | About page | Are the founders technical? | Choice | yes / no / unknown | +10 for yes (scaled down below 0.7 confidence). "Unknown" (the page doesn't name the founders) scores nothing and shows "Founders: unknown" |
| 10 | About page | Is this their first sales hire? | Choice | yes / no / unknown | +30 for yes, only if #7 found an open sales role (scaled down below 0.7 confidence). Jev sees the open role titles; "unknown" is only offered when none are open, and scores nothing |
| 11 | Investigation | Enough evidence, or dig further? | Choice | score now / check careers / search news / fetch about page (only options not yet tried) | Gathers that evidence and re-asks #2–#6; at most 3 rounds |

### Jev's three question types

Jev ("TypeSafe Jev", through the `langchain-typesafe` package) answers typed
questions about a piece of text. Raised uses all three types:

| Type | Use it for | What Jev returns | How Raised reads it |
|---|---|---|---|
| **Noul** | A yes/no question | The **probability the answer is yes** (0–1), nothing else | "yes" if the probability is 0.5 or more, else "no". Confidence is the probability of the side chosen, so it's never below 0.5 (0.9 yes → "yes, 0.9"; 0.2 yes → "no, 0.8") |
| **Choice** | Picking one label from a list, in no particular order | The label, a probability for **every** label, and a confidence | The label and its confidence |
| **Score** | A position on an ordered rubric (level 0, 1, 2 …) | The **expected** level (can be fractional, e.g. 2.7), a probability per level, and a confidence | The level and its confidence |

- **Why some yes/no questions are Choice, not Noul:** a Noul can only say yes
  or no. Technical founders (#9) and first sales hire (#10) need a third answer,
  "unknown", for when the page simply doesn't say, so they're Choice questions
  with `yes` / `no` / `unknown` labels.
- **Several questions share one call.** Jev answers a whole set of questions
  about the same text at once: #2–#6 in one call per company, #7–#8 in one call
  per job, #9–#10 in one call per company, and #1 and #11 on their own. Before
  each run, a one-question Noul checks that Jev is reachable and paid up.
- **What Jev sees** is short text Raised assembles: the extracted funding facts,
  plus job descriptions, about/careers page excerpts or news headlines as
  relevant. Never the full article.

**Jev can do more that Raised doesn't use yet:**
- The **per-label and per-level probabilities** from Choice and Score (for
  example, how much of a B2B/B2C answer is really "Both").
- **Descriptions for the yes and no outcomes** of a Noul question
  (`NoulCriteria`).
- **Structured JSON input** instead of plain text.
- **Token usage** per request, for tracking Jev's cost.
- **Experimental agent middleware:** scoring the risk of an agent's tool calls
  (`AutoModeMiddleware`) and routing requests between models
  (`ModelRouterMiddleware`).

**How the answers are used:**
- **Rejections** (#1–#3) need a "no" with at least 0.7 confidence. #2–#3 are
  checked once, before investigation, and are skipped if they would reject more
  than half of a batch of 4 or more (that points to a model problem, not bad
  companies).
- **Re-asked questions** (#2–#6 during investigation): the latest answer is the
  one that counts.
- **Scaled points** (#9, #10): full points at 0.7 confidence or more; below
  that, `points × confidence ÷ 0.7`, rounded. The score breakdown shows it, e.g.
  "First sales hire (confidence 0.36) +15 (reduced from 30)".
- **Which jobs Jev sees** (#7–#8): only titles or departments that look like
  sales, at most 20 per company. Partnerships, customer success, account
  management, marketing, general management, consulting and solutions
  engineering count as "Other".

**Jev doesn't decide:** what an article says (Claude), whether a domain is
real, dates and freshness, duplicates, which jobs look like sales, or the point
values and cut-offs (all plain Python).

### Ideal customer (ICP)

Jev places each company on this rubric: *"a B2B company at Seed to Series B
that is building a sales function for the first time."*

| Step | Meaning |
|---:|---|
| 0 | Consumer, not B2B, or wrong stage |
| 1 | Weak fit |
| 2 | B2B, but stage or sales motion unclear |
| 3 | B2B, right stage, some go-to-market signal |
| 4 | B2B at Seed–Series B, clearly building sales for the first time |

Points are `20 × step ÷ 4`, rounded (step 2.7 → 14 points). To change who
counts as ideal, edit the question in `pipeline/src/judge.py`.

---

## Scoring

Points are additive (max **120**) — not a percentage.

| Signal | Points |
|---|---:|
| Raise recency (fades to 0 over 90 days) | 0–30 |
| Seed, Series A or Series B | +15 |
| Open direct sales role (AE, SDR/BDR, sales leadership) | +15 |
| …and it's their first sales hire | +30 more* |
| Technical founders | +10* |
| ICP fit | 0–20 |

\* Full points at 0.7 confidence or more, scaled down below that
([details](#what-jev-decides)).

Automatically hidden: confident B2C companies, "Later"-round companies with more
than $200M raised, articles that don't announce a new round, records that
clearly aren't a startup raising money, and anything whose raise is older than
90 days. Hidden companies are kept in the database, never deleted.

Weights live in [`pipeline/src/config.py`](pipeline/src/config.py).

---

## Deployment

- **Dashboard** → Vercel, with root directory `dashboard/` and `SUPABASE_URL` +
  `SUPABASE_ANON_KEY` set.
- **Pipeline** → [GitHub Actions](.github/workflows/daily.yml), daily at
  **13:00 UTC**. Needs secrets `ANTHROPIC_API_KEY`, `TYPESAFE_API_KEY` and
  `DATABASE_URL`. The variable `EDGAR_USER_AGENT` (an app name and contact
  email, which the SEC asks for) is optional; a generic one is used without it.
  - `DATABASE_URL` must be Supabase's **Session pooler** URL: GitHub runners
    can't reach the direct database host, which is IPv6-only.
  - If Claude or Jev runs out of funds, the run stops before saving anything and
    picks up again once funds are added. Failures don't open GitHub issues.

Details: [docs/operations.md](docs/operations.md#deployment).

---

## More docs

- [How it works](docs/how-it-works.md): the pipeline, models, date rules, scoring and database
- [Operations](docs/operations.md): deployment, testing and known limitations
