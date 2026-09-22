"""Postgres (Supabase) persistence via psycopg."""

from __future__ import annotations

import json
import logging
from datetime import date

import psycopg

from . import config
from .models import Company

log = logging.getLogger(__name__)


def get_conn() -> psycopg.Connection:
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(config.DATABASE_URL)


def known_dedupe_keys(conn: psycopg.Connection) -> set[str]:
    """Dedupe keys plus normalized names of every company already stored."""
    rows = conn.execute(
        "select dedupe_key, lower(regexp_replace(name, '[^a-zA-Z0-9]', '', 'g')) from companies"
    ).fetchall()
    return {k for r in rows for k in r if k}


def upsert_company(conn: psycopg.Connection, c: Company) -> int:
    row = conn.execute(
        """
        insert into companies (name, domain, dedupe_key, round, amount_raised, raised_date)
        values (%s, %s, %s, %s, %s, %s)
        on conflict (dedupe_key) do update set
            name          = excluded.name,
            domain        = coalesce(excluded.domain, companies.domain),
            round         = excluded.round,
            amount_raised = excluded.amount_raised,
            raised_date   = excluded.raised_date
        returning id
        """,
        (c.name, c.domain, c.dedupe_key, c.round.value, c.amount_raised, c.raised_date),
    ).fetchone()
    return row[0]


def persist_run(companies: list[Company], run_date: date) -> None:
    with get_conn() as conn, conn.transaction():
        for c in companies:
            c.id = upsert_company(conn, c)
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
    log.info("persisted %d companies for run %s", len(companies), run_date)


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
