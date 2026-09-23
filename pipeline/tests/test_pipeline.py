import unittest
from contextlib import ExitStack
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src import config, dates, extract, main
from src.models import Company, FeedItem


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_company_is_judged_before_stale_records_are_filtered(self):
        today = dates.now_utc().date()
        fresh = Company(name="Fresh", dedupe_key="fresh", source_url="", raised_date=today, article_published_at=today, funding_evidence="announcement")
        stale = fresh.model_copy(update={"name":"Old", "dedupe_key":"old", "raised_date":today - timedelta(days=config.DISPLAY_WINDOW_DAYS + 1)})
        with patch("src.judge.judge_new_round", new_callable=AsyncMock) as judge:
            eligible = await main._screen([fresh, stale])
        self.assertEqual(judge.await_count, 2)
        self.assertEqual(eligible, [fresh])
        self.assertEqual(stale.rejection_reason, "stale")

    async def test_daily_and_backfill_choose_their_config_windows(self):
        for argv, expected, backfill in [(["run"], config.INGEST_WINDOW_DAYS, False), (["run", "--backfill"], config.BACKFILL_WINDOW_DAYS, True)]:
            with self.subTest(argv=argv), ExitStack() as stack:
                discover = stack.enter_context(patch.object(main, "_discover", new_callable=AsyncMock, return_value=[]))
                stack.enter_context(patch.object(main, "_dedupe_against_db", new_callable=AsyncMock, return_value=[]))
                stack.enter_context(patch.object(main.db, "migrate"))
                stack.enter_context(patch.object(main.db, "backfill_completed", return_value=False))
                age_out = stack.enter_context(patch.object(main.db, "exclude_aged_out"))
                persist = stack.enter_context(patch.object(main.db, "persist_run", return_value={}))
                stack.enter_context(patch.object(main.db, "dashboard_summary", return_value={}))
                stack.enter_context(patch("src.jobs.fetch_all_jobs", new_callable=AsyncMock))
                stack.enter_context(patch("src.judge.judge_all", new_callable=AsyncMock))
                stack.enter_context(patch("src.judge.preflight", new_callable=AsyncMock))
                stack.enter_context(patch("src.llm.preflight", new_callable=AsyncMock))
                stack.enter_context(patch("src.investigate.investigate_all", new_callable=AsyncMock))
                stack.enter_context(patch("builtins.print"))
                await main.main(argv)
                discover.assert_awaited_once_with(False, expected, {})
                age_out.assert_called_once()
                self.assertEqual(persist.call_args.kwargs["backfill"], backfill)

    async def test_gate_rejections_are_persisted_but_not_investigated(self):
        today = dates.now_utc().date()
        keep = Company(name="Keep", dedupe_key="keep", source_url="", raised_date=today, article_published_at=today, funding_evidence="a")
        bar = keep.model_copy(update={"name": "Bar", "dedupe_key": "bar"})

        async def judge_all(companies):
            bar.rejection_reason = "not_startup_raise"

        with ExitStack() as stack:
            stack.enter_context(patch.object(main, "_discover", new_callable=AsyncMock, return_value=[keep, bar]))
            stack.enter_context(patch.object(main, "_dedupe_against_db", new_callable=AsyncMock, side_effect=lambda c: c))
            for name in ("migrate", "exclude_aged_out"):
                stack.enter_context(patch.object(main.db, name))
            persist = stack.enter_context(patch.object(main.db, "persist_run", return_value={}))
            stack.enter_context(patch.object(main.db, "dashboard_summary", return_value={}))
            stack.enter_context(patch("src.judge.judge_new_round", new_callable=AsyncMock))
            stack.enter_context(patch("src.jobs.fetch_all_jobs", new_callable=AsyncMock))
            stack.enter_context(patch("src.judge.judge_all", side_effect=judge_all))
            stack.enter_context(patch("src.judge.preflight", new_callable=AsyncMock))
            stack.enter_context(patch("src.llm.preflight", new_callable=AsyncMock))
            investigate = stack.enter_context(patch("src.investigate.investigate_all", new_callable=AsyncMock))
            stack.enter_context(patch("builtins.print"))
            await main.main(["run"])
        self.assertEqual([c.name for c in investigate.await_args.args[0]], ["Keep"])
        self.assertEqual([c.name for c in persist.call_args.args[0]], ["Keep", "Bar"])
        self.assertGreater(keep.score, 0)
        self.assertEqual(bar.score, 0)

    async def test_completed_backfill_stops_before_discovery(self):
        with patch.object(main.db, "migrate"), patch.object(main.db, "backfill_completed", return_value=True), patch.object(main, "_discover", new_callable=AsyncMock) as discover, \
             patch("src.llm.preflight", new_callable=AsyncMock), patch("src.judge.preflight", new_callable=AsyncMock):
            with self.assertRaises(SystemExit):
                await main.main(["run", "--backfill"])
        discover.assert_not_awaited()

    async def test_model_failures_abort_instead_of_seeding_empty_data(self):
        item = FeedItem(title="Article", url="https://example.com/article", published=date(2026, 9, 22), source="test", text="An article")
        with patch.object(extract.llm, "complete_json", new_callable=AsyncMock, side_effect=RuntimeError("provider unavailable")):
            with self.assertRaises(RuntimeError):
                await extract.extract_one(item)

    def test_cron_does_not_backfill(self):
        workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "daily.yml"
        text = workflow.read_text()
        self.assertIn("python -m src.main run", text)
        self.assertNotIn("--backfill", text)


if __name__ == "__main__":
    unittest.main()
