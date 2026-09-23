# How Raised works

Detailed reference for the pipeline, models, date rules, scoring and storage.
For setup, see the [README](../README.md).

- [Architecture](#architecture)
- [Models](#models)
- [Jev in detail](#jev-in-detail)
- [Pipeline stages](#pipeline-stages)
- [Date windows](#date-windows)
- [Rejection and age-out](#rejection-and-age-out)
- [Scoring](#scoring)
- [Database](#database)
- [Dashboard](#dashboard)

---

## Architecture

```mermaid
flowchart TD
    Schedule["GitHub Actions: daily at 13:00 UTC<br/>or manual Python CLI"]

    subgraph Pipeline["Python pipeline"]
        Prepare["Apply migration and age-out rules"]
        Sources["TechCrunch RSS / Google News RSS / SEC EDGAR<br/>Filter publication and filing dates"]
        Fetch["Fetch article text<br/>Recheck original publication date"]
        Extract["Claude Sonnet 4.5<br/>Extract a newly announced funding round"]
        Identity["Python<br/>Verify domain and deduplicate"]
        Gate["Jev: is this a new round?<br/>Python: date and evidence checks"]
        Enrich["Public job boards, company pages and news"]
        Judge["Jev<br/>Company / sales-role judgments<br/>Bounded investigation decisions"]
        Founders["Jev<br/>Technical founders / first sales hire"]
        Score["Python<br/>Exclusions, weighted score and explanation"]
        Reject["Record rejection reason and evidence<br/>Exclude company without deleting it"]
    end

    Schedule --> Prepare --> Sources --> Fetch --> Extract --> Identity --> Gate
    Gate -->|Eligible| Enrich --> Judge
    Judge -->|Gather more evidence| Enrich
    Judge -->|Score now or investigation budget exhausted| Founders --> Score
    Gate -->|Rejected or unverifiable| Reject
    Score --> Database[("Supabase Postgres")]
    Reject --> Database

    subgraph Web["Next.js dashboard on Vercel"]
        Read["Server-side Supabase reads<br/>ranked_companies + signals + decisions"]
        Table["React table<br/>Filters, sorting, details and email template"]
        Logos["Node.js /api/logo endpoint<br/>Validated and cached favicon lookup"]
    end

    Database --> Read --> Table
    Table -->|Logo request| Logos
```

The diagram shows a full `run`. Diagnostic commands stop at earlier stages.

| Layer | Technology | Responsibility |
|---|---|---|
| Ingestion | Python 3.12, asyncio, httpx, feedparser, Beautiful Soup | Fetch feeds/pages, enforce windows, verify domains, dedupe, enrich |
| Extraction | Anthropic SDK + Pydantic | Turn article text into validated funding fields |
| Judgment | TypeSafe Jev via `langchain-typesafe` | Typed classifications, confidence and investigation choices |
| Scoring | Plain Python | Weights, exclusions, ordering and explanation text |
| Storage | Supabase Postgres + psycopg | Companies, signals, scores, decisions, rejections |
| Dashboard | Next.js 16, React 19, TypeScript, Tailwind 4, Lucide | Server-rendered data, client-side table |
| Hosting | Vercel + GitHub Actions | Web app and scheduled pipeline run separately |

---

## Models

The default Anthropic model is **Claude Sonnet 4.5** (`claude-sonnet-4-5`).
Judgments use **TypeSafe Jev** via `TypeSafeClassifier()`, with the installed
SDK's default service configuration (no separate Jev version is pinned).

| Task | Model | Input → output |
|---|---|---|
| Funding extraction | Claude | Article title, date and text → company, domain, round, USD amount, announcement date, investors, supporting quote (or `not_funding_article`) |
| New-round check | Jev | Funding evidence + claimed round → is this a new round, not an older one? |
| Company judgments | Jev | Company facts + enrichment → genuine raise, startup, B2B/B2C/Both/Unclear, round label, ICP fit. What each answer changes: [Jev in detail](#jev-in-detail) |
| Job classification | Jev | Job title, department, description → sales or not; AE, SDR, Head of Sales or Other |
| Founder / first hire | Jev | About/team page → technical founder, first sales hire |
| Investigation | Jev | Current evidence → `score_now`, `check_careers`, `search_news` or `fetch_about` |
| Alternative judge (opt-in) | Claude | Same questions via `LLMBackend`, only with an explicit `JUDGE_BACKEND=llm` |
| Score, explanation, email, logos | No model | Python, a TypeScript template and favicon lookup |

Code: [extraction](../pipeline/src/extract.py) ·
[Anthropic client](../pipeline/src/llm.py) · [judges](../pipeline/src/judge.py) ·
[scoring](../pipeline/src/score.py) · [email template](../dashboard/lib/map.ts)

### Model behavior

- **Extraction** uses a forced `return_json` tool call with the Pydantic
  `FundingExtraction` schema, then validates it.
- Article text is capped at **12,000 characters**. Only the round newly
  announced in the article is extracted. A missing announcement date falls back
  to the article's publication date — never today's date.
- **Jev** receives extracted fields plus short job, about/careers and news
  excerpts — not the full article.
- Jev `Noul` answers become yes/no plus confidence; `Choice` gives categories;
  `Score` gives the ICP position. Anything below **0.7** confidence (**0.4**
  for ICP fit) is flagged `needs_review`; "unknown" answers are never flagged.
- **Jev judges, always.** A missing `TYPESAFE_API_KEY` or a Jev that won't
  start stops the run; it never falls back to Claude on its own. A one-call
  preflight checks the judge before extraction spends anything. Set
  `JUDGE_BACKEND=llm` only to judge with Claude on purpose.
- `ANTHROPIC_MODEL` overrides the Claude model used for extraction.
- **Failures:** at most 8 model calls run at once. Rate limits, overloads and
  timeouts are retried with backoff. A company that still fails is skipped for
  the run; if over 25% of a stage fails, the run aborts before writing
  anything. Invalid extracted records are logged and skipped.

---

## Jev in detail

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

## Pipeline stages

1. **Prepare** — check the Claude and Jev accounts with a one-token call each
   (out of funds or a bad key stops the run here, before any database write),
   then apply migrations/settings and age out old companies.
2. **Discover** — TechCrunch venture/startups RSS; Google News for
   `raises Seed`, `raises Series A`, `raises Series B`; SEC EDGAR Form D
   full-text search. Dates are filtered before fetching. Google News redirect
   URLs are decoded with `googlenewsdecoder`. Articles already processed on an
   earlier run (see `processed_articles`) are skipped before fetching, so each
   article is paid for once rather than on every day of the 3-day lookback.
3. **Extract** — fetch the article, prefer the publisher's original date over
   the feed date, recheck the window, and call Claude.
4. **Identity** — pick domain candidates from the article and check the homepage
   mentions the company. Unverified domains are cleared and flagged. Dedupe by
   URL, then verified domain/normalized name, then existing database records.
5. **Screen** — new-round check plus deterministic date/evidence rules.
6. **Enrich and judge** — guess job-board slugs and try
   **Ashby → Greenhouse → Lever**, stopping at the first non-empty list. Jev
   judges the company, and each job whose title or department looks like sales
   (at most 20 per company). Other jobs only count toward "open roles".
7. **Investigate** — prefetch `/about`, `/team`, `/about-us` or `/company`; Jev
   decides whether to score or gather more (`/careers`, `/jobs`, news). At most
   **3 enrichment rounds**. Founder/first-hire judgments run afterwards.
8. **Rank and save** — apply exclusions and weights, then write scores, signals,
   decisions and rejections to Postgres.

---

## Date windows

Defined in [`pipeline/src/config.py`](../pipeline/src/config.py).

| Setting | Default | Purpose |
|---|---:|---|
| `INGEST_WINDOW_DAYS` | 3 | Daily article lookback |
| `DISPLAY_WINDOW_DAYS` | 90 | How long a raise stays on the dashboard |
| `BACKFILL_WINDOW_DAYS` | 30 | One-time seed lookback |
| `MAX_ARTICLE_LAG_DAYS` | 7 | Max gap between the raise and the article |

- RSS uses UTC `pubDate`. Missing, out-of-window and future dates are skipped;
  `updated` is never used in its place.
- Google searches use `when:3d` (or `when:30d` for backfill). EDGAR gets the
  matching filing-date range.
- Per-source counts (fetched, too old, missing date, kept) are logged.

---

## Rejection and age-out

| Condition | Result |
|---|---|
| Raise too old, too far before its article, or in the future | Rejected as `stale` |
| Jev says "not a new round" with ≥ 0.7 confidence | Rejected as `not_new_round` |
| Jev says "not a funding raise" or "not a startup" with ≥ 0.7 confidence | Rejected as `not_startup_raise`, unless it would reject over half of a batch of 4+ (treated as a model problem and skipped) |
| Missing raise date, article date or evidence; or future article date | Quarantined as `source_unverifiable` |
| New-round answer is uncertain | Flagged for review; continues if date checks pass |
| Company passes the 90-day cutoff on a later run | `excluded = true`, reason `aged out` |

Rejections go to `rejected_companies` with snapshots. Company rows are
**excluded, never deleted**.

### `cleanup`

Re-fetches stored companies' sources, recovers publication dates, re-extracts
funding evidence and reruns the new-round check. It may correct an announcement
date (keeping the old one in the evidence JSON). It does **not** recompute
scores and never invents missing dates.

---

## Scoring

Additive points, max **120**. Values are in `SCORING_WEIGHTS` in
[config](../pipeline/src/config.py).

| Rule | Points |
|---|---:|
| Raise recency | 0–30 |
| Seed, Series A or Series B | +15 |
| First sales hire **and** an open sales role | +30 |
| Any open sales role | +15 |
| Technical founder | +10 |
| ICP fit (Jev's 0–4 scale) | 0–20 |

- Recency: `max(0, round(30 * (1 - days_since_raise / 90)))`
- ICP: `round(20 * clamp(raw_icp / 4, 0, 1))`
- Sort order: score ↓, raise age ↑, average signal confidence ↓.
- **Excluded from ranking** (but kept): B2C with ≥ 0.7 confidence, and `later`
  rounds with more than **$200M** raised.
- Low-confidence findings stay visible for review; confidence doesn't reduce
  points.

---

## Database

| Table / view | Holds |
|---|---|
| `companies` | Identity, verified-domain flag, round, amount, dates, source, evidence, exclusion state |
| `signals` | Append-only judgments with confidence, review flags and sources |
| `scores` | Score, explanation and fired rules; one per company per `run_date` |
| `decisions` | Investigation questions, actions, confidence and round numbers |
| `rejected_companies` | Rejection/quarantine history with snapshots |
| `pipeline_settings` | Display window, one-time backfill status and last successful run |
| `pipeline_status` | Read-only view of the last successful run time, for the dashboard |
| `processed_articles` | Article URLs with a final outcome, skipped on later runs; pruned after 60 days |
| `ranked_companies` | Each company's latest score, filtered for display |

`ranked_companies` hides excluded companies, raises outside the display window,
future raises and missing/future article dates. It uses each company's **latest
score across all runs**, not just the latest run.

---

## Dashboard

- The Next.js page reads `ranked_companies`, `signals` and `decisions` on the
  server (paginated). Filtering, sorting and copying happen in the browser.
- Email drafts are a fixed TypeScript template. Nothing sends email.
- **Logos:** `/api/logo` (validated, cached Google favicon) → the company's
  `/favicon.ico` → initials. Unverified domains go straight to initials.
