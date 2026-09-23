"""Postgres (Supabase) persistence via psycopg."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from . import config
from .models import Company

log = logging.getLogger(__name__)


def get_conn() -> psycopg.Connection:
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(config.DATABASE_URL)


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def migrate() -> None:
    """Apply every migration in order. Each file is idempotent, so re-running is safe."""
    with get_conn() as conn:
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            conn.execute(migration.read_text())
        conn.execute(
            "insert into pipeline_settings(singleton, display_window_days) values (true, %s) "
            "on conflict (singleton) do update set display_window_days=excluded.display_window_days",
            (config.DISPLAY_WINDOW_DAYS,),
        )


def backfill_completed() -> bool:
    with get_conn() as conn:
        return conn.execute("select backfill_completed_at is not null from pipeline_settings where singleton").fetchone()[0]


def age_out(conn: psycopg.Connection, today: date) -> list[tuple]:
    cutoff = today - timedelta(days=config.DISPLAY_WINDOW_DAYS)
    return conn.execute(
        "update companies set excluded=true, excluded_reason='aged out' "
        "where raised_date < %s and (not excluded or excluded_reason is distinct from 'aged out') "
        "returning id, name, raised_date", (cutoff,),
    ).fetchall()


def exclude_aged_out(today: date) -> list[tuple]:
    with get_conn() as conn:
        rows = age_out(conn, today)
    log.info("aged out %d companies", len(rows))
    return rows


def load_existing() -> list[Company]:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute("""
            select c.id, c.name, c.domain, c.domain_verified, c.dedupe_key,
                   coalesce(c.round, 'unknown') as round, c.amount_raised, c.raised_date,
                   c.article_published_at, coalesce(c.article_title, '') as article_title,
                   coalesce(c.funding_evidence, '') as funding_evidence,
                   c.excluded, c.excluded_reason,
                   coalesce(nullif(c.source_url, ''), (
                       select s.source_url from signals s where s.company_id=c.id
                       and s.signal_type in ('genuine_raise', 'is_startup', 'round', 'domain_unverified', 'sells_to', 'icp_fit')
                       and s.source_url is not null and s.source_url <> '' order by s.id limit 1
                   ), '') as source_url
            from companies c order by c.id
        """).fetchall()
    return [Company.model_validate(row) for row in rows]


def dashboard_summary() -> dict:
    with get_conn() as conn:
        count, oldest, newest = conn.execute("select count(*), min(raised_date), max(raised_date) from ranked_companies").fetchone()
    return {"companies": count, "oldest_raise": str(oldest) if oldest else None, "newest_raise": str(newest) if newest else None}


def known_article_urls() -> set[str]:
    """Normalized URLs whose outcome is final, plus every stored company's
    source article (covers rows saved before processed_articles existed)."""
    from .fetch import normalize_url

    with get_conn() as conn:
        processed = {r[0] for r in conn.execute("select url from processed_articles")}
        sources = conn.execute("select source_url from companies where coalesce(source_url, '') <> ''").fetchall()
    return processed | {normalize_url(r[0]) for r in sources}


def known_dedupe_keys(conn: psycopg.Connection) -> set[str]:
    """Dedupe keys plus normalized names of every company already stored."""
    rows = conn.execute(
        "select dedupe_key, lower(regexp_replace(name, '[^a-zA-Z0-9]', '', 'g')) from companies"
    ).fetchall()
    return {k for r in rows for k in r if k}


def upsert_company(conn: psycopg.Connection, c: Company) -> int:
    row = conn.execute(
        """
        insert into companies (name, domain, domain_verified, dedupe_key, round,
                               amount_raised, raised_date, excluded, excluded_reason,
                               article_published_at, source_url, article_title, funding_evidence)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (dedupe_key) do update set
            name            = excluded.name,
            domain          = excluded.domain,
            domain_verified = excluded.domain_verified,
            round           = excluded.round,
            amount_raised   = excluded.amount_raised,
            raised_date     = excluded.raised_date,
            excluded        = excluded.excluded,
            excluded_reason = excluded.excluded_reason,
            article_published_at = excluded.article_published_at,
            source_url      = excluded.source_url,
            article_title   = excluded.article_title,
            funding_evidence = excluded.funding_evidence
        returning id
        """,
        (c.name, c.domain, c.domain_verified, c.dedupe_key, c.round.value,
         c.amount_raised, c.raised_date, c.excluded, c.excluded_reason,
         c.article_published_at, c.source_url, c.article_title, c.funding_evidence),
    ).fetchone()
    return row[0]


def _rejection_confidence(c: Company) -> float:
    if c.rejection_reason == "stale":
        return 1.0  # a date rule, not a judgment
    if c.rejection_reason == "not_startup_raise":
        from .judge import _gate_signal

        signal = _gate_signal(c)
    else:
        signal = next((s for s in reversed(c.signals) if s.signal_type == "new_round"), None)
    return signal.confidence if signal else 0.0


def persist_run(
    companies: list[Company],
    run_date: date,
    *,
    backfill: bool = False,
    write_scores: bool = True,
    processed_articles: dict[str, str] | None = None,
) -> dict:
    """Everything in one transaction: an aborted run marks no article processed."""
    added = rejected = 0
    with get_conn() as conn, conn.transaction():
        if backfill:
            completed = conn.execute("select backfill_completed_at from pipeline_settings where singleton for update").fetchone()[0]
            if completed is not None:
                raise RuntimeError("The one-time backfill has already completed")
        known = {row[0] for row in conn.execute("select dedupe_key from companies").fetchall()}
        for c in companies:
            is_new = c.dedupe_key not in known
            c.id = upsert_company(conn, c)
            known.add(c.dedupe_key)
            if is_new and not c.rejection_reason:
                added += 1
            if c.rejection_reason:
                rejected += 1
                confidence = _rejection_confidence(c)
                conn.execute("""
                    insert into rejected_companies
                        (company_id, name, reason, confidence, source_url, run_date,
                         raised_date, article_published_at, details, snapshot)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (company_id, reason, run_date) do update set
                        confidence=excluded.confidence, details=excluded.details,
                        raised_date=excluded.raised_date, article_published_at=excluded.article_published_at,
                        snapshot=excluded.snapshot
                """, (c.id, c.name, c.rejection_reason, confidence, c.source_url, run_date,
                       c.raised_date, c.article_published_at, c.rejection_detail, c.model_dump_json()))
            for s in c.signals:
                conn.execute(
                    """
                    insert into signals
                        (company_id, signal_type, value, confidence, needs_review, source_url, detected_at)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (c.id, s.signal_type, s.value, s.confidence, s.needs_review,
                     s.source_url, s.detected_at),
                )
            for d in c.decisions:
                conn.execute(
                    """
                    insert into decisions
                        (company_id, question, answer, confidence, action_chosen, round, created_at)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (c.id, d.question, d.answer, d.confidence,
                     d.action_chosen, d.round, d.created_at),
                )
            if not write_scores or c.rejection_reason:
                continue
            conn.execute(
                """
                insert into scores (company_id, score, explanation, rules_fired, run_date)
                values (%s, %s, %s, %s, %s)
                on conflict (company_id, run_date) do update set
                    score = excluded.score,
                    explanation = excluded.explanation,
                    rules_fired = excluded.rules_fired
                """,
                (c.id, c.score, c.explanation, json.dumps(c.rules_fired), run_date),
            )
        if processed_articles:
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into processed_articles (url, outcome) values (%s, %s) on conflict (url) do nothing",
                    list(processed_articles.items()),
                )
        conn.execute(
            "delete from processed_articles where first_seen < now() - make_interval(days => %s)",
            (config.PROCESSED_ARTICLE_RETENTION_DAYS,),
        )
        aged = age_out(conn, run_date)
        if write_scores:  # a real run, not cleanup; committed with its results
            conn.execute("update pipeline_settings set last_run_completed_at=now() where singleton")
        if backfill:
            conn.execute("update pipeline_settings set backfill_completed_at=now(), backfill_added_count=%s where singleton", (added,))
    log.info("persisted %d companies for run %s; added=%d rejected=%d aged_out=%d", len(companies), run_date, added, rejected, len(aged))
    return {"added": added, "rejected": rejected, "aged_out": len(aged)}


def fetch_ranked(run_date: date | None = None) -> list[dict]:
    with get_conn() as conn:
        if run_date is None:
            row = conn.execute("select max(run_date) from scores").fetchone()
            run_date = row[0]
            if run_date is None:
                return []
        rows = conn.execute(
            """
            select c.name, c.domain, c.round, c.amount_raised, c.raised_date,
                   s.score, s.explanation, s.rules_fired
            from scores s join companies c on c.id = s.company_id
            where s.run_date = %s
            order by s.score desc
            """,
            (run_date,),
        ).fetchall()
    return [
        {
            "name": r[0], "domain": r[1], "round": r[2],
            "amount_raised": float(r[3]) if r[3] is not None else None,
            "raised_date": r[4].isoformat() if r[4] else None,
            "score": r[5], "explanation": r[6], "rules_fired": r[7],
        }
        for r in rows
    ]
