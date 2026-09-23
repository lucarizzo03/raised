import os
import unittest
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

import psycopg
from psycopg import sql

from src import config, dates, db
from src.models import Company


@unittest.skipUnless(os.environ.get("RUN_DATABASE_TESTS") == "1", "opt-in PostgreSQL temporary-table tests")
class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(config.DATABASE_URL, connect_timeout=10)
        self.addCleanup(self.conn.close)
        transaction = self.conn.transaction(force_rollback=True)
        transaction.__enter__()
        self.addCleanup(transaction.__exit__, None, None, None)
        self.conn.execute("set local search_path to pg_temp")
        self.conn.execute("set local timezone to 'UTC'")
        for name in ("companies", "signals", "scores", "decisions", "rejected_companies"):
            self.conn.execute(sql.SQL("create temporary table {} (like public.{} including all)").format(sql.Identifier(name), sql.Identifier(name)))

        @contextmanager
        def connection():
            yield self.conn

        replacement = patch.object(db, "get_conn", connection)
        replacement.start()
        self.addCleanup(replacement.stop)
        db.migrate()
        self.today = dates.now_utc().date()

    def company(self, name="Acme", age=0):
        raised = self.today - timedelta(days=age)
        return Company(name=name, dedupe_key=name.lower(), source_url="https://example.com/article", raised_date=raised, article_published_at=raised, funding_evidence="announcement", score=50)

    def test_migration_and_view_use_config(self):
        db.migrate()
        c = self.company()
        db.persist_run([c], self.today)
        self.assertEqual(db.dashboard_summary()["companies"], 1)
        self.assertEqual(self.conn.execute("select display_window_days from pipeline_settings").fetchone()[0], config.DISPLAY_WINDOW_DAYS)
        namespaces = self.conn.execute("select n.nspname from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.oid in ('companies'::regclass, 'ranked_companies'::regclass, 'pipeline_settings'::regclass)").fetchall()
        self.assertTrue(all(n[0].startswith("pg_temp_") for n in namespaces))

    def test_heartbeat_is_set_by_runs_not_cleanup(self):
        status = "select last_run_completed_at from pipeline_status"
        db.persist_run([self.company()], self.today, write_scores=False)
        self.assertIsNone(self.conn.execute(status).fetchone()[0])
        db.persist_run([], self.today)  # a run that found nothing still counts
        self.assertIsNotNone(self.conn.execute(status).fetchone()[0])

    def test_processed_articles_are_saved_read_back_and_pruned(self):
        db.persist_run([self.company()], self.today, processed_articles={"https://news.example.com/op-ed": "not_funding"})
        known = db.known_article_urls()
        self.assertIn("https://news.example.com/op-ed", known)
        self.assertIn("https://example.com/article", known)  # company source, normalized
        self.conn.execute("update processed_articles set first_seen = now() - interval '61 days'")
        db.persist_run([], self.today)
        self.assertEqual(self.conn.execute("select count(*) from processed_articles").fetchone()[0], 0)

    def test_rejected_companies_has_row_level_security(self):
        enabled = self.conn.execute("select relrowsecurity from pg_class where oid = 'rejected_companies'::regclass").fetchone()[0]
        self.assertTrue(enabled)

    def test_age_out_retains_company_and_score(self):
        c = self.company()
        db.persist_run([c], self.today)
        self.conn.execute("update companies set raised_date=%s", (self.today - timedelta(days=config.DISPLAY_WINDOW_DAYS + 1),))
        rows = db.exclude_aged_out(self.today)
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.conn.execute("select excluded, excluded_reason from companies").fetchone(), (True, "aged out"))
        self.assertEqual(self.conn.execute("select count(*) from scores").fetchone()[0], 1)
        self.assertEqual(db.dashboard_summary()["companies"], 0)

    def test_rejections_preserve_evidence_and_are_idempotent(self):
        c = self.company(age=config.DISPLAY_WINDOW_DAYS + 1)
        dates.apply_rejection(c, self.today)
        db.persist_run([c], self.today, write_scores=False)
        db.persist_run([c], self.today, write_scores=False)
        row = self.conn.execute("select name, reason, raised_date, article_published_at, snapshot from rejected_companies").fetchone()
        self.assertEqual(row[:4], (c.name, "stale", c.raised_date, c.article_published_at))
        self.assertEqual(row[4]["funding_evidence"], "announcement")
        self.assertEqual(self.conn.execute("select count(*) from companies").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("select count(*) from rejected_companies").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("select count(*) from scores").fetchone()[0], 0)

    def test_backfill_is_one_time_and_daily_runs_do_not_mark_it(self):
        db.persist_run([self.company()], self.today)
        self.assertFalse(db.backfill_completed())
        result = db.persist_run([self.company("Beta")], self.today, backfill=True)
        self.assertEqual(result["added"], 1)
        self.assertTrue(db.backfill_completed())
        with self.assertRaises(RuntimeError):
            db.persist_run([], self.today, backfill=True)
        self.assertEqual(self.conn.execute("select count(*) from companies").fetchone()[0], 2)

    def test_view_hides_records_without_a_publication_date(self):
        c = self.company()
        c.article_published_at = None
        db.persist_run([c], self.today)
        self.assertEqual(self.conn.execute("select count(*) from companies").fetchone()[0], 1)
        self.assertEqual(db.dashboard_summary()["companies"], 0)

    def test_cleanup_does_not_replace_existing_scores(self):
        c = self.company()
        db.persist_run([c], self.today)
        c.score = 0
        db.persist_run([c], self.today, write_scores=False)
        self.assertEqual(self.conn.execute("select score from scores").fetchone()[0], 50)


if __name__ == "__main__":
    unittest.main()
