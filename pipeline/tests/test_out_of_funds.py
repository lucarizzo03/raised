import logging
import os
import tempfile
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import anthropic
import httpx2
from langchain_typesafe.client import TypeSafeAPIError

from src import extract, judge, llm, main, resilience
from src.models import FeedItem

TODAY = date(2026, 9, 22)


def anthropic_error(status, message, cls=anthropic.BadRequestError):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": message}}
    return cls(message, response=httpx2.Response(status, request=request), body=body)


# The exact refusal from the 2026-09-22 run.
NO_CREDIT = anthropic_error(400, "Your credit balance is too low to access the Anthropic API. "
                                 "Please go to Plans & Billing to upgrade or purchase credits.")


class DetectionTests(unittest.TestCase):
    def test_billing_refusals_are_recognized(self):
        self.assertTrue(resilience.is_out_of_funds(NO_CREDIT))
        self.assertTrue(resilience.is_out_of_funds(TypeSafeAPIError(402, {"error": "Payment Required"}, httpx2.Headers())))
        self.assertTrue(resilience.is_out_of_funds(TypeSafeAPIError(403, {"error": "insufficient credit"}, httpx2.Headers())))

    def test_other_errors_are_not_mistaken_for_billing(self):
        self.assertFalse(resilience.is_out_of_funds(anthropic_error(400, "max_tokens: field required")))
        self.assertFalse(resilience.is_out_of_funds(anthropic_error(429, "rate limit exceeded", anthropic.RateLimitError)))
        self.assertFalse(resilience.is_out_of_funds(TimeoutError()))
        self.assertFalse(resilience.is_out_of_funds(RuntimeError("credit balance")))  # no status: not an API refusal

    def test_provider_is_named(self):
        self.assertEqual(resilience.provider_name(NO_CREDIT), "Anthropic (Claude)")
        self.assertEqual(resilience.provider_name(TypeSafeAPIError(402, None, httpx2.Headers())), "TypeSafe (Jev)")


class StopImmediatelyTests(unittest.IsolatedAsyncioTestCase):
    async def test_billing_errors_are_not_retried(self):
        call = AsyncMock(side_effect=NO_CREDIT)
        with self.assertRaises(anthropic.BadRequestError):
            await resilience.with_retries(call, what="test")
        self.assertEqual(call.await_count, 1)

    async def test_one_refusal_stops_the_stage_even_below_the_failure_threshold(self):
        async def fn(i):
            if i == 9:
                raise NO_CREDIT
            return i

        with self.assertRaises(resilience.OutOfFunds):  # 1 of 10 would normally be tolerated
            await resilience.run_each(range(10), fn, stage="extract")

    async def test_credit_running_out_mid_extraction_stops_the_run(self):
        items = [FeedItem(title=f"a{i}", url=f"https://n.example.com/{i}", published=TODAY, source="t", text="x")
                 for i in range(10)]
        replies = [{"company_name": f"Co{i}"} for i in range(9)] + [NO_CREDIT]
        with patch.object(extract.llm, "complete_json", AsyncMock(side_effect=replies)), \
             patch.object(extract, "now_utc", return_value=SimpleNamespace(date=lambda: TODAY)):
            with self.assertRaises(resilience.OutOfFunds):
                await extract.extract_companies(items)

    async def test_claude_preflight_turns_a_refusal_into_out_of_funds(self):
        client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=NO_CREDIT)))
        with patch.object(llm, "_client", return_value=client):
            with self.assertRaisesRegex(resilience.OutOfFunds, "Anthropic"):
                await llm.preflight()

    async def test_jev_preflight_turns_a_refusal_into_out_of_funds(self):
        refused = TypeSafeAPIError(402, None, httpx2.Headers())
        with patch.object(judge, "backend", return_value=SimpleNamespace(ask=AsyncMock(side_effect=refused))), \
             patch.object(judge, "_questions", return_value={}):
            with self.assertRaisesRegex(resilience.OutOfFunds, "Jev"):
                await judge.preflight()


class NothingIsWrittenTests(unittest.TestCase):
    def run_cli(self, **patches):
        with patch.object(main.db, "migrate") as migrate, \
             patch.object(main.db, "exclude_aged_out") as age_out, \
             patch.object(main.db, "persist_run") as persist, \
             patch.object(main, "_discover", AsyncMock(return_value=[])) as discover, \
             patch("src.llm.preflight", patches.get("claude", AsyncMock())), \
             patch("src.judge.preflight", patches.get("jev", AsyncMock())):
            with self.assertRaises(SystemExit) as exit_, self.assertLogs("src.main", logging.ERROR) as logs:
                main.cli(["run"])
        return exit_.exception.code, logs.output[0], migrate, age_out, persist, discover

    def test_empty_balance_stops_before_touching_the_database(self):
        for provider in ("claude", "jev"):
            with self.subTest(provider=provider):
                refusal = AsyncMock(side_effect=resilience.OutOfFunds("Anthropic (Claude) account is out of funds"))
                code, message, migrate, age_out, persist, discover = self.run_cli(**{provider: refusal})
                self.assertEqual(code, 3)
                self.assertIn("existing data is unchanged", message)
                for untouched in (migrate, age_out, persist, discover):
                    untouched.assert_not_called()

    def test_github_run_summary_explains_the_stop(self):
        with tempfile.NamedTemporaryFile("r", suffix=".md") as summary, \
             patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary.name}):
            self.run_cli(claude=AsyncMock(side_effect=resilience.OutOfFunds("Anthropic (Claude) account is out of funds")))
            self.assertIn("Out of funds", summary.read())


if __name__ == "__main__":
    unittest.main()
