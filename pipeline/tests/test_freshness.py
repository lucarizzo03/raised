import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote

from src import config, dates, extract, feeds, judge
from src.models import Company, FeedItem, FundingExtraction, Round, Signal


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 9, 22)

    def test_date_boundaries(self):
        self.assertIsNone(dates.date_violation(self.today, self.today, self.today))
        self.assertIsNone(dates.date_violation(self.today - timedelta(days=config.DISPLAY_WINDOW_DAYS), None, self.today))
        self.assertEqual(dates.date_violation(self.today - timedelta(days=config.DISPLAY_WINDOW_DAYS + 1), None, self.today), "outside_display_window")
        self.assertEqual(dates.date_violation(self.today + timedelta(days=1), self.today, self.today), "future_dated")
        self.assertIsNone(dates.date_violation(self.today - timedelta(days=config.MAX_ARTICLE_LAG_DAYS), self.today, self.today))
        self.assertEqual(dates.date_violation(self.today - timedelta(days=config.MAX_ARTICLE_LAG_DAYS + 1), self.today, self.today), "article_lag")

    def test_publication_metadata_never_uses_modified_date(self):
        html = '<meta property="article:modified_time" content="2026-09-22"><script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-09-18T10:00:00Z"}</script>'
        self.assertEqual(dates.article_publication_date(html), date(2026, 9, 18))
        self.assertIsNone(dates.article_publication_date('<meta property="article:modified_time" content="2026-09-22">'))

    def test_missing_dates_are_not_invented(self):
        self.assertIsNone(dates.article_publication_date('<html>Unknown publication date</html>'))

    def test_stale_company_is_rejected_without_a_signal(self):
        company = Company(name="Old Co", dedupe_key="old", source_url="", raised_date=date(2013, 1, 1))
        dates.apply_rejection(company, self.today)
        self.assertTrue(company.excluded)
        self.assertEqual(company.rejection_reason, "stale")

    def test_new_round_confidence_gate(self):
        company = Company(name="Acme", dedupe_key="acme", source_url="", raised_date=self.today, article_published_at=self.today, funding_evidence="announcement")
        company.signals = [Signal(signal_type="new_round", value="no", confidence=config.CONFIDENCE_REVIEW_THRESHOLD)]
        dates.apply_rejection(company, self.today)
        self.assertEqual(company.rejection_reason, "not_new_round")
        company.signals = [Signal(signal_type="new_round", value="no", confidence=config.CONFIDENCE_REVIEW_THRESHOLD - .01, needs_review=True)]
        dates.apply_rejection(company, self.today)
        self.assertIsNone(company.rejection_reason)

    def test_unverifiable_records_are_quarantined(self):
        company = Company(name="Acme", dedupe_key="acme", source_url="", raised_date=self.today)
        dates.apply_rejection(company, self.today)
        self.assertEqual(company.rejection_reason, "source_unverifiable")
        self.assertTrue(company.excluded)


class FeedTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)

    def entry(self, name, age=None):
        entry = {"title": name, "link": f"https://example.com/{name}"}
        if age is not None:
            entry["published_parsed"] = (self.now - timedelta(days=age)).utctimetuple()
        return entry

    async def test_rss_filters_before_article_fetching(self):
        entries = [self.entry("recent", 0), self.entry("boundary", config.INGEST_WINDOW_DAYS), self.entry("old", config.INGEST_WINDOW_DAYS + 1), self.entry("undated")]
        with patch.object(feeds, "now_utc", return_value=self.now), patch.object(config, "TECHCRUNCH_FEEDS", ["https://example.com/feed"]), patch.object(feeds.feedparser, "parse", return_value=SimpleNamespace(entries=entries)):
            with self.assertLogs("src.feeds", level="INFO") as logs:
                items = await feeds.fetch_techcrunch()
        self.assertEqual([i.title for i in items], ["recent", "boundary"])
        self.assertIn("fetched=4", " ".join(logs.output))
        self.assertIn("skipped_too_old=1", " ".join(logs.output))
        self.assertIn("skipped_missing_date=1", " ".join(logs.output))

    async def test_updated_date_is_not_a_publication_date(self):
        entry = self.entry("undated")
        entry["updated_parsed"] = self.now.utctimetuple()
        with patch.object(feeds, "now_utc", return_value=self.now), patch.object(config, "TECHCRUNCH_FEEDS", ["https://example.com/feed"]), patch.object(feeds.feedparser, "parse", return_value=SimpleNamespace(entries=[entry])):
            self.assertEqual(await feeds.fetch_techcrunch(), [])

    async def test_google_window_and_pre_decode_filtering(self):
        entries = [self.entry("recent", 0), self.entry("old", config.INGEST_WINDOW_DAYS + 1)]
        with patch.object(feeds, "now_utc", return_value=self.now), patch.object(feeds.feedparser, "parse", return_value=SimpleNamespace(entries=entries)) as parse, patch.object(feeds, "_resolve_google_news_urls", new_callable=AsyncMock) as decode:
            items = await feeds.fetch_google_news()
        self.assertTrue(all(f"when:{config.INGEST_WINDOW_DAYS}d" in unquote(call.args[0]) for call in parse.call_args_list))
        self.assertEqual([i.title for i in items], ["recent"])
        self.assertEqual([i.title for i in decode.call_args.args[0]], ["recent"])

    async def test_backfill_window(self):
        entries = [self.entry("older", config.BACKFILL_WINDOW_DAYS - 1)]
        with patch.object(feeds, "now_utc", return_value=self.now), patch.object(feeds.feedparser, "parse", return_value=SimpleNamespace(entries=entries)) as parse, patch.object(feeds, "_resolve_google_news_urls", new_callable=AsyncMock):
            items = await feeds.fetch_google_news(config.BACKFILL_WINDOW_DAYS)
        self.assertEqual(len(items), 1)
        self.assertTrue(all(f"when:{config.BACKFILL_WINDOW_DAYS}d" in unquote(call.args[0]) for call in parse.call_args_list))

    async def test_edgar_range(self):
        client = AsyncMock()
        response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"hits": {"hits": []}})
        client.get.return_value = response
        with patch.object(feeds, "now_utc", return_value=self.now), patch.object(feeds.httpx, "AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            await feeds.fetch_edgar()
        params = client.get.call_args.kwargs["params"]
        self.assertEqual(params["startdt"], (self.now.date() - timedelta(days=config.INGEST_WINDOW_DAYS)).isoformat())
        self.assertEqual(params["enddt"], self.now.date().isoformat())


class ExtractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_recent_feed_cannot_refresh_an_old_article(self):
        item = FeedItem(title="Plaid Series A", url="https://example.com/old", published=date(2026, 9, 22), source="google_news")
        fetcher = SimpleNamespace(get_text_html=AsyncMock(return_value=("Plaid announced Series A.", '<meta property="article:published_time" content="2013-09-19">')), close=AsyncMock())
        with patch.object(extract, "Fetcher", return_value=fetcher), patch.object(extract, "extract_one", new_callable=AsyncMock) as model:
            companies = await extract.extract_companies([item])
        self.assertEqual(item.published, date(2013, 9, 19))
        self.assertEqual(companies, [])
        model.assert_not_awaited()

    async def test_publish_date_is_sent_and_used_as_fallback(self):
        item = FeedItem(title="Acme raises Seed", url="https://example.com/article", published=date(2026, 9, 22), source="techcrunch", text="Acme today announced a seed round.")
        with patch.object(extract.llm, "complete_json", new_callable=AsyncMock, return_value={"company_name": "Acme", "round": "seed", "announcement_evidence": "Acme today announced a seed round."}) as complete:
            result = await extract.extract_one(item)
        self.assertEqual(result.raised_date, item.published)
        self.assertIn(item.published.isoformat(), complete.call_args.args[1])
        self.assertIn("background", complete.call_args.args[0])

    async def test_stated_announcement_date_is_preserved(self):
        item = FeedItem(title="Acme raises", url="", published=date(2026, 9, 22), source="techcrunch", text="Acme announced the round on September 20.")
        with patch.object(extract.llm, "complete_json", new_callable=AsyncMock, return_value={"company_name":"Acme", "raised_date":"2026-09-20"}):
            result = await extract.extract_one(item)
        self.assertEqual(result.raised_date, date(2026, 9, 20))

    async def test_new_round_judgment_marks_uncertainty(self):
        company = Company(name="Acme", dedupe_key="acme", source_url="https://example.com", funding_evidence="Acme announced Seed", article_published_at=date(2026, 9, 22))
        backend = SimpleNamespace(ask=AsyncMock(return_value={"new_round":judge.Judgment("no", .6)}))
        with patch.object(judge, "backend", return_value=backend):
            await judge.judge_new_round(company)
        self.assertEqual(company.signals[-1].signal_type, "new_round")
        self.assertTrue(company.signals[-1].needs_review)
        self.assertIn("2026-09-22", backend.ask.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
