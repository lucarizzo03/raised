# Raised

Finds recently funded startups that look ready to build a sales team, and ranks
them for outreach.

**[Open the dashboard →](https://raised-lac.vercel.app)**

> **Claude extracts. Jev judges. Python scores. Supabase stores. Next.js displays.**

## How it works

Every day at 13:00 UTC, GitHub Actions runs the pipeline:

1. **Check:** make sure the Claude and Jev accounts work. If either is out of funds, stop and save nothing.
2. **Discover:** pull new articles from TechCrunch, Google News and SEC filings (last 3 days; each article is read only once).
3. **Extract:** Claude Sonnet 4.5 pulls out the company, round, amount and date.
4. **Verify:** Python confirms the company's website and drops duplicates and stale rounds.
5. **Judge:** Jev answers the questions below.
6. **Score & save:** Python adds up the points and saves everything to Supabase.

The website (Next.js on Vercel) only reads the database. It never runs the pipeline or calls a model.

## What Jev decides

Jev makes every judgment call. It answers three kinds of question: **Noul** (yes/no, returned as the probability of yes), **Choice** (pick one label) and **Score** (a position on a 0–4 rubric).

| Jev decides | Type | What happens |
|---|---|---|
| Is this article announcing a **new** round? | Noul | Confident "no" → rejected |
| Is it a real company raising money? A tech startup? | Noul | Confident "no" → rejected |
| Sells to B2B, B2C, both, or unclear? | Choice | Confident B2C → hidden |
| Which round? | Choice | Seed–Series B → +15. "Later" over $200M → hidden |
| How well does it fit the ideal customer (B2B, Seed–B, building sales)? | Score | 0–20 points |
| For each sales-looking job: is it direct sales (AE, SDR, sales leader)? | Noul + Choice | Any yes → +15 |
| Are the founders technical? (yes / no / unknown) | Choice | Yes → +10 |
| Is this their first sales hire? (yes / no / unknown) | Choice | Yes → +30, if a sales role is open |
| Enough evidence, or dig further? | Choice | Check careers, news or about page (up to 3 rounds) |

- **Confidence:** answers under 0.7 are flagged "needs review" (0.4 for ICP fit, 0.5 for sells-to). The +30 and +10 scale down below 0.7. "Unknown" scores nothing.
- **Not Jev's job:** Claude only reads articles. Python handles websites, dates, duplicates and all the points.

Full details: [Jev in detail](docs/how-it-works.md#jev-in-detail).

## Scoring (max 120)

Recency 0–30 · Seed–Series B +15 · Open sales role +15 · First sales hire +30 · Technical founders +10 · ICP fit 0–20

Hidden, but kept in the database: confident B2C, "Later" rounds over $200M, articles that aren't a new round, non-startups, and raises older than 90 days.

## Running it

- **Pipeline:** GitHub Actions ([`daily.yml`](.github/workflows/daily.yml)). Secrets: `ANTHROPIC_API_KEY`, `TYPESAFE_API_KEY`, `DATABASE_URL` (use Supabase's **Session pooler** URL; GitHub can't reach the direct one).
- **Dashboard:** Vercel, root directory `dashboard/`, with `SUPABASE_URL` and `SUPABASE_ANON_KEY`.

More: [how it works](docs/how-it-works.md) · [operations, testing and limits](docs/operations.md)
