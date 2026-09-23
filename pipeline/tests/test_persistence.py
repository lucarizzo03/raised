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

    def test_rescore_replaces_founder_answers_and_reflags(self):
        from src.models import Signal
        c = self.company()
        c.signals = [Signal(signal_type="technical_founders", value="yes", confidence=0.52, needs_review=True),
                     Signal(signal_type="icp_fit", value="2.5", confidence=0.55, needs_review=True),
                     Signal(signal_type="sells_to", value="B2B", confidence=0.6, needs_review=True),
                     Signal(signal_type="sales_role", value="yes (AE)", confidence=0.9)]
        db.persist_run([c], self.today - timedelta(days=1))
        loaded = [x for x in db.load_scored_companies() if x.id == c.id][0]
        self.assertEqual(len(loaded.signals), 4)
        loaded.signals = [s for s in loaded.signals if s.signal_type not in db.FOUNDER_SIGNALS] + [
            Signal(signal_type="technical_founders", value="unknown", confidence=0.9)]
        loaded.score, loaded.explanation, loaded.rules_fired = 42, "rescored", ["x"]
        db.save_rescore([loaded], self.today)
        rows = dict(self.conn.execute("select signal_type, value from signals where company_id=%s", (c.id,)).fetchall())
        self.assertEqual(rows["technical_founders"], "unknown")  # old guess replaced, not kept
        self.assertEqual(rows["sales_role"], "yes (AE)")          # other answers untouched
        flags = dict(self.conn.execute("select signal_type, needs_review from signals where company_id=%s", (c.id,)).fetchall())
        self.assertFalse(flags["icp_fit"])   # 0.55 clears the 0.4 ICP bar
        self.assertFalse(flags["sells_to"])  # 0.6 clears the 0.5 sells-to bar
        self.assertEqual(self.conn.execute("select score from ranked_companies where company_id=%s", (c.id,)).fetchone()[0], 42)

    def test_rescore_replaces_job_answers_only_when_rejudged(self):
        from src.models import Signal
        a, b = self.company("A"), self.company("B")
        for c in (a, b):
            c.signals = [Signal(signal_type="sales_role", value="yes (Head of Germany)", confidence=0.8, source_url="j1")]
        db.persist_run([a, b], self.today - timedelta(days=1))
        loaded = {x.id: x for x in db.load_scored_companies() if x.id in (a.id, b.id)}
        for c in loaded.values():
            c.signals = [Signal(signal_type="sales_role", value="no (Head of Germany)", confidence=0.9, source_url="j1")]
            c.score, c.explanation, c.rules_fired = 1, "", []
        db.save_rescore(list(loaded.values()), self.today, rejudged_jobs={a.id})
        values = {cid: [r[0] for r in self.conn.execute("select value from signals where company_id=%s and signal_type='sales_role'", (cid,))]
                  for cid in (a.id, b.id)}
        self.assertEqual(values[a.id], ["no (Head of Germany)"])   # re-judged: replaced
        self.assertEqual(values[b.id], ["yes (Head of Germany)"])  # board returned nothing: kept

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
