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

from . import config, dates, db
from .models import Company
from .resilience import run_each

log = logging.getLogger(__name__)


async def _discover(mock: bool, window_days: int = config.INGEST_WINDOW_DAYS) -> list[Company]:
    from . import extract, feeds

    if mock:
        return _mock_companies()
    items = await feeds.fetch_all_feeds(window_days)
    return await extract.extract_companies(items, window_days)


async def _dedupe_against_db(companies: list[Company]) -> list[Company]:
    try:
        with db.get_conn() as conn:
            known = db.known_dedupe_keys(conn)
    except Exception as exc:
        log.warning("db dedupe skipped: %s", exc)
        return companies
    from .fetch import normalize_name

    fresh = [
        c for c in companies
        if c.dedupe_key not in known and normalize_name(c.name) not in known
    ]
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
        c.article_published_at = date.today()
        c.funding_evidence = "Mock funding announcement"
        c.signals = [
            Signal(signal_type="new_round", value="yes", confidence=0.95, source_url=c.source_url),
            Signal(signal_type="genuine_raise", value="yes", confidence=0.95, source_url=c.source_url),
            Signal(signal_type="sales_role", value="yes (Account Executive)", confidence=0.9,
                   source_url="https://jobs.ashbyhq.com/acmedata/1"),
            Signal(signal_type="first_sales_hire", value="yes", confidence=0.8),
            Signal(signal_type="technical_founders", value="yes", confidence=0.85),
        ]
    return cos


def _print_rejections(companies: list[Company]) -> None:
    for c in companies:
        if c.rejection_reason:
            print(f"REJECTED | {c.name} | raised={c.raised_date} | article={c.article_published_at} | {c.rejection_reason}: {c.rejection_detail}")


async def _screen(companies: list[Company], mock: bool = False) -> list[Company]:
    from .judge import judge_new_round

    async def screen(company):
        if not mock:
            await judge_new_round(company)
        dates.apply_rejection(company)

    _, failed = await run_each(companies, screen, stage="screen", label=lambda c: c.name)
    for c in failed:
        c.failed_stage = "screen"
    return [c for c in companies if not c.rejection_reason and not c.failed_stage]


def _without_failed(companies: list[Company]) -> list[Company]:
    """Failed companies are not persisted; the next run rediscovers them."""
    return [c for c in companies if not c.failed_stage]


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", default="run", choices=["discover", "jobs", "judge", "score", "run", "ranked", "migrate", "cleanup"])
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--mock-models", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.backfill and args.command != "run":
        parser.error("--backfill is only supported for run")
    if args.mock_models and args.command in {"run", "cleanup"}:
        parser.error("--mock-models cannot write to the database; use score to preview")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not args.verbose:
        for name in ("httpx", "httpx2"):
            logging.getLogger(name).setLevel(logging.WARNING)
    today = dates.now_utc().date()
    if args.command in {"run", "cleanup", "migrate"}:
        db.migrate()
    if args.command == "migrate":
        print("date-window migration applied")
        return
    if args.command == "cleanup":
        from .cleanup import audit_existing

        companies = await audit_existing()
        result = db.persist_run(companies, today, write_scores=False)
        _print_rejections(companies)
        print(f"Cleanup: {result}")
        print(f"Dashboard: {db.dashboard_summary()}")
        return
    if args.command == "run":
        if args.backfill and db.backfill_completed():
            parser.error("The one-time backfill has already completed")
        db.exclude_aged_out(today)

    if args.command == "ranked":
        for i, r in enumerate(db.fetch_ranked(), 1):
            print(f"{i:3d}. {r['score']:3d}  {r['name']:30s} {r['explanation']}")
        return

    from . import investigate, jobs as jobs_mod, judge, score

    window_days = config.BACKFILL_WINDOW_DAYS if args.backfill else config.INGEST_WINDOW_DAYS
    log.info("pipeline mode=%s window_days=%d", "backfill" if args.backfill else "daily", window_days)
    companies = await _discover(args.mock_models, window_days)
    companies = await _dedupe_against_db(companies)

    if args.command == "discover":
        _print_companies(companies)
        return

    eligible = await _screen(companies, args.mock_models)
    await jobs_mod.fetch_all_jobs(eligible)
    if args.command == "jobs":
        _print_jobs(eligible)
        return

    if not args.mock_models:
        await judge.judge_all(eligible)
    # Gate rejections are persisted with the rest but never investigated or scored.
    eligible = [c for c in eligible if not c.rejection_reason]
    if args.command == "judge":
        # Fetch about pages so founder/first-hire judgments print too.
        if not args.mock_models:
            from .fetch import Fetcher

            fetcher = Fetcher()
            try:
                await asyncio.gather(
                    *(investigate._fetch_about(c, fetcher) for c in eligible)
                )
            finally:
                await fetcher.close()
            await asyncio.gather(*(judge.judge_founders(c) for c in eligible))
        _print_signals(companies)
        return

    if not args.mock_models:
        await investigate.investigate_all(eligible)
    companies = _without_failed(companies)
    eligible = _without_failed(eligible)
    ranked = score.rank(eligible)  # scores everything, returns the visible set
    _print_rejections(companies)
    excluded = [c for c in companies if c.excluded]
    _print_ranked(ranked[: config.TOP_N])
    if excluded:
        print(f"\n{len(excluded)} excluded from the ranking:")
        for c in excluded:
            print(f"    {c.name:30s} {c.excluded_reason}")

    if args.command == "run":
        # Excluded companies stay on record with the flag set; only the
        # ranking hides them.
        result = db.persist_run(companies, today, backfill=args.backfill)
        print(f"persisted run {today} ({len(ranked)} ranked, {len(excluded)} excluded)")
        print(f"{'Backfill' if args.backfill else 'Daily'}: {result}")
        print(f"Dashboard: {db.dashboard_summary()}")


if __name__ == "__main__":
    asyncio.run(main())
