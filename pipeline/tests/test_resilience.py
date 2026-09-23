import asyncio
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src import config, extract, investigate, judge, main, resilience
from src.models import Company, FeedItem


class Transient(Exception):
    status_code = 529


class Permanent(Exception):
    status_code = 400


def company(name: str) -> Company:
    today = date(2026, 9, 22)
    return Company(name=name, dedupe_key=name.lower(), source_url="https://example.com/" + name,
                   raised_date=today, article_published_at=today, funding_evidence="announcement")


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        sleep = patch.object(resilience.asyncio, "sleep", new_callable=AsyncMock)
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    async def test_transient_errors_are_retried_then_succeed(self):
        call = AsyncMock(side_effect=[Transient(), TimeoutError(), "ok"])
        self.assertEqual(await resilience.with_retries(call, what="test"), "ok")
        self.assertEqual(call.await_count, 3)

    async def test_permanent_errors_are_not_retried(self):
        call = AsyncMock(side_effect=Permanent())
        with self.assertRaises(Permanent):
            await resilience.with_retries(call, what="test")
        self.assertEqual(call.await_count, 1)

    async def test_retries_are_bounded(self):
        call = AsyncMock(side_effect=Transient())
        with self.assertRaises(Transient):
            await resilience.with_retries(call, what="test")
        self.assertEqual(call.await_count, config.MODEL_MAX_RETRIES + 1)

    async def test_server_retry_after_is_honored(self):
        exc = Transient()
        exc.retry_after_ms = 2500
        call = AsyncMock(side_effect=[exc, "ok"])
        await resilience.with_retries(call, what="test")
        self.sleep.assert_awaited_once_with(2.5)

    def test_transient_classification(self):
        self.assertTrue(resilience.is_transient(SimpleNamespace(status_code=429)))
        self.assertTrue(resilience.is_transient(SimpleNamespace(status=503)))
        self.assertTrue(resilience.is_transient(ConnectionError()))
        self.assertFalse(resilience.is_transient(SimpleNamespace(status_code=401)))
        self.assertFalse(resilience.is_transient(ValueError()))

    async def test_jev_backend_retries_transient_failures(self):
        answers = SimpleNamespace(answers={"q": SimpleNamespace(type="noul", noul=0.9)})
        backend = judge.JevBackend.__new__(judge.JevBackend)
        backend._clf = SimpleNamespace(ainvoke=AsyncMock(side_effect=[Transient(), answers]))
        result = await backend.ask("state", {})
        self.assertEqual(result["q"].value, "yes")
        self.assertEqual(backend._clf.ainvoke.await_count, 2)


class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_calls_share_one_concurrency_cap(self):
        active = peak = 0

        async def fake_ainvoke(_):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return SimpleNamespace(answers={})

        backend = judge.JevBackend.__new__(judge.JevBackend)
        backend._clf = SimpleNamespace(ainvoke=fake_ainvoke)
        await asyncio.gather(*(backend.ask("s", {}) for _ in range(config.MODEL_MAX_CONCURRENCY * 3)))
        self.assertEqual(peak, config.MODEL_MAX_CONCURRENCY)


class IsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_failure_is_isolated(self):
        async def fn(i):
            if i == 2:
                raise RuntimeError("boom")
            return i * 10

        results, failed = await resilience.run_each(range(5), fn, stage="test")
        self.assertEqual(results, [0, 10, None, 30, 40])
        self.assertEqual(failed, [2])

    async def test_widespread_failure_aborts_the_stage(self):
        async def fn(i):
            raise RuntimeError("provider down")

        with self.assertRaises(resilience.StageFailure):
            await resilience.run_each(range(4), fn, stage="test")

    async def test_cancellation_is_not_swallowed(self):
        async def fn(i):
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await resilience.run_each([1], fn, stage="test")

    async def test_extraction_skips_one_bad_article(self):
        today = date(2026, 9, 22)
        items = [FeedItem(title=f"a{i}", url=f"https://example.com/{i}", published=today, source="t", text="x") for i in range(5)]
        good = {"company_name": "Acme", "round": "seed"}
        calls = AsyncMock(side_effect=[good, good, RuntimeError("bad"), good, good])
        with patch.object(extract.llm, "complete_json", calls), \
             patch.object(extract, "now_utc", return_value=SimpleNamespace(date=lambda: today)), \
             patch.object(extract.domains, "pick_domain", return_value=(None, "none")):
            companies = await extract.extract_companies(items)
        self.assertEqual(calls.await_count, 5)
        self.assertEqual([c.name for c in companies], ["Acme"])  # deduped by name

    async def test_extraction_aborts_when_the_provider_is_down(self):
        today = date(2026, 9, 22)
        items = [FeedItem(title="a", url="https://example.com/a", published=today, source="t", text="x")]
        with patch.object(extract.llm, "complete_json", AsyncMock(side_effect=RuntimeError("down"))), \
             patch.object(extract, "now_utc", return_value=SimpleNamespace(date=lambda: today)):
            with self.assertRaises(resilience.StageFailure):
                await extract.extract_companies(items)

    async def test_failed_company_is_dropped_but_others_are_judged(self):
        companies = [company(n) for n in "ABCDE"]

        async def judge_company(c):
            if c.name == "C":
                raise RuntimeError("bad payload")

        with patch.object(judge, "judge_company", judge_company):
            await judge.judge_all(companies)
        self.assertEqual([c.name for c in companies if c.failed_stage], ["C"])
        self.assertEqual(companies[2].failed_stage, "judge")
        self.assertEqual(main._without_failed(companies), [companies[i] for i in (0, 1, 3, 4)])

    async def test_screen_drops_failed_companies(self):
        companies = [company(n) for n in "ABCDE"]

        async def judge_new_round(c):
            if c.name == "B":
                raise RuntimeError("timeout")

        with patch.object(judge, "judge_new_round", judge_new_round):
            eligible = await main._screen(companies)
        self.assertEqual([c.name for c in eligible], ["A", "C", "D", "E"])
        self.assertEqual(companies[1].failed_stage, "screen")

    async def test_investigation_skips_already_failed_companies(self):
        companies = [company(n) for n in "ABCD"]
        companies[0].failed_stage = "judge"
        seen = []

        async def investigate_company(c, fetcher):
            seen.append(c.name)

        with patch.object(investigate, "investigate_company", investigate_company), \
             patch.object(investigate, "judge_founders", AsyncMock()):
            await investigate.investigate_all(companies)
        self.assertEqual(sorted(seen), ["B", "C", "D"])

    def test_failed_stage_is_not_in_snapshots(self):
        c = company("A")
        c.failed_stage = "judge"
        self.assertNotIn("failed_stage", c.model_dump_json())


if __name__ == "__main__":
    unittest.main()
