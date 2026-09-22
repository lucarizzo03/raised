"""Pipeline CLI.

  python -m src.main discover   # feeds -> fetch -> extract -> dedupe (prints list)
  python -m src.main jobs       # + job boards (prints open roles)
  python -m src.main judge      # + Jev judgments (prints signals w/ confidence)
  python -m src.main score      # + investigation loop + scoring (prints ranking)
  python -m src.main run        # everything + persist to Postgres
  python -m src.main ranked     # print latest ranking from the DB

  --mock-models stubs extraction/judgments so the plumbing can be verified
  without API keys.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date

from . import config, db
from .models import Company

log = logging.getLogger(__name__)


async def _discover(mock: bool) -> list[Company]:
    from . import extract, feeds

    items = await feeds.fetch_all_feeds()
    if mock:
        return _mock_companies()
    return await extract.extract_companies(items)


async def _dedupe_against_db(companies: list[Company]) -> list[Company]:
    try:
        known = db.known_dedupe_keys(db.get_conn())
    except Exception as exc:
        log.warning("db dedupe skipped: %s", exc)
        return companies
    fresh = [c for c in companies if c.dedupe_key not in known]
    log.info("db dedupe: %d new, %d already known", len(fresh), len(companies) - len(fresh))
    return fresh


def _print_companies(companies: list[Company]) -> None:
    for c in companies:
        amt = f"${c.amount_raised/1e6:.1f}M" if c.amount_raised else "?"
        print(f"  {c.name:30s} {c.domain or '-':28s} {c.round.value:9s} {amt:>9s} {c.source_url}")
    print(f"{len(companies)} companies")


def _print_jobs(companies: list[Company]) -> None:
    for c in companies:
        print(f"{c.name} ({len(c.jobs)} open roles)")
        for j in c.jobs:
            print(f"    [{j.board}] {j.title} — {j.url}")


def _print_signals(companies: list[Company]) -> None:
    for c in companies:
        print(f"{c.name}")
        for s in c.signals:
            flag = "  [needs_review]" if s.needs_review else ""
            print(f"    {s.signal_type:20s} {s.value:50s} conf={s.confidence:.2f}{flag}")


def _print_ranked(companies: list[Company]) -> None:
    for i, c in enumerate(companies, 1):
        print(f"{i:3d}. {c.score:3d}  {c.name:30s} {c.explanation}")


def _mock_companies() -> list[Company]:
    from .models import JobPosting, Signal

    cos = [
        Company(name="Acme Data", domain="acmedata.com", dedupe_key="acmedata.com",
                round=__import__("src.models", fromlist=["Round"]).Round.SEED,
                amount_raised=8_000_000, raised_date=date.today(),
                investors=["Example Capital"], source_url="https://example.com/acme",
                jobs=[JobPosting(title="Account Executive", url="https://jobs.ashbyhq.com/acmedata/1",
                                 board="ashby")],
                about_text="Founded by two ex-Google engineers."),
        Company(name="Beta Cloud", domain="betacloud.io", dedupe_key="betacloud.io",
                round=__import__("src.models", fromlist=["Round"]).Round.SERIES_A,
                amount_raised=20_000_000, raised_date=date.today(),
                investors=["Fund"], source_url="https://example.com/beta"),
    ]
    for c in cos:
        c.signals = [
            Signal(signal_type="genuine_raise", value="yes", confidence=0.95, source_url=c.source_url),
            Signal(signal_type="sales_role", value="yes (Account Executive)", confidence=0.9,
                   source_url="https://jobs.ashbyhq.com/acmedata/1"),
            Signal(signal_type="first_sales_hire", value="yes", confidence=0.8),
            Signal(signal_type="technical_founders", value="yes", confidence=0.85),
        ]
    return cos


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["discover", "jobs", "judge", "score", "run", "ranked"])
    parser.add_argument("--mock-models", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "ranked":
        for i, r in enumerate(db.fetch_ranked(), 1):
            print(f"{i:3d}. {r['score']:3d}  {r['name']:30s} {r['explanation']}")
        return

    from . import investigate, jobs as jobs_mod, judge, score

    companies = await _discover(args.mock_models)
    companies = await _dedupe_against_db(companies)

    if args.command == "discover":
        _print_companies(companies)
        return

    await jobs_mod.fetch_all_jobs(companies)
    if args.command == "jobs":
        _print_jobs(companies)
        return

    if not args.mock_models:
        await judge.judge_all(companies)
    if args.command == "judge":
        # Fetch about pages so founder/first-hire judgments print too.
        if not args.mock_models:
            from .fetch import Fetcher

            fetcher = Fetcher()
            try:
                await asyncio.gather(
                    *(investigate._fetch_about(c, fetcher) for c in companies)
                )
            finally:
                await fetcher.close()
            await asyncio.gather(*(judge.judge_founders(c) for c in companies))
        _print_signals(companies)
        return

    if not args.mock_models:
        await investigate.investigate_all(companies)
    ranked = score.rank(companies)
    _print_ranked(ranked)

    if args.command == "run":
        db.persist_run(ranked, date.today())
        print(f"persisted run {date.today()} ({len(ranked)} companies)")


if __name__ == "__main__":
    asyncio.run(main())
