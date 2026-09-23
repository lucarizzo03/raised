import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src import config, judge, score
from src.judge import Judgment
from src.models import Company


def company(**kw):
    return Company(name="Acme", dedupe_key="acme", source_url="", raised_date=date(2026, 9, 22),
                   about_text="Acme builds payroll software.", **kw)


def record(signal_type, value, confidence):
    c = company()
    judge._record(c, signal_type, Judgment(value, confidence), None)
    return c.signals[-1]


class ThresholdTests(unittest.TestCase):
    def test_icp_uses_its_own_lower_bar(self):
        self.assertEqual(config.REVIEW_THRESHOLDS["icp_fit"], 0.4)
        self.assertTrue(record("icp_fit", "1.05", 0.12).needs_review)
        self.assertTrue(record("icp_fit", "1.37", 0.39).needs_review)
        self.assertFalse(record("icp_fit", "2.42", 0.48).needs_review)  # torn between steps: fine
        self.assertFalse(record("icp_fit", "2.71", 0.55).needs_review)

    def test_other_questions_keep_the_0_7_bar(self):
        for signal_type in ("genuine_raise", "is_startup", "sells_to", "round", "sales_role",
                            "sales_role_type", "first_sales_hire", "technical_founders", "new_round"):
            with self.subTest(signal_type=signal_type):
                self.assertTrue(record(signal_type, "yes", 0.69).needs_review)
                self.assertFalse(record(signal_type, "yes", 0.70).needs_review)

    def test_decision_thresholds_are_unchanged(self):
        # The flag moved; rejecting and hiding still need 0.7 confidence.
        self.assertEqual(config.CONFIDENCE_REVIEW_THRESHOLD, 0.7)
        self.assertEqual(config.B2C_EXCLUDE_CONFIDENCE, 0.7)


class UnknownFoundersTests(unittest.IsolatedAsyncioTestCase):
    async def judge_founders(self, technical, confidence):
        answers = {"technical_founders": Judgment(technical, confidence), "first_sales_hire": Judgment("no", 0.9)}
        c = company()
        with patch.object(judge, "backend", return_value=SimpleNamespace(ask=AsyncMock(return_value=answers))), \
             patch.object(judge, "_questions", side_effect=lambda **q: q):
            await judge.judge_founders(c)
        return c

    async def test_question_offers_unknown(self):
        questions = {}

        async def ask(state, qs):
            questions.update(qs)
            return {"technical_founders": Judgment("unknown", 0.9), "first_sales_hire": Judgment("no", 0.9)}

        with patch.object(judge, "backend", return_value=SimpleNamespace(ask=ask)), \
             patch.object(judge, "_questions", side_effect=lambda **q: q):
            await judge.judge_founders(company())
        kind, spec = questions["technical_founders"]
        self.assertEqual(kind, "choice")
        self.assertEqual(set(spec["criteria"]), {"yes", "no", "unknown"})

    async def test_unknown_is_not_flagged_and_not_scored(self):
        c = await self.judge_founders("unknown", 0.35)
        sig = next(s for s in c.signals if s.signal_type == "technical_founders")
        self.assertEqual(sig.value, "unknown")
        self.assertFalse(sig.needs_review)  # low confidence, but missing data isn't reviewable
        with patch.object(score, "now_utc", return_value=SimpleNamespace(date=lambda: date(2026, 9, 22))):
            score.score_company(c)
        self.assertNotIn("technical_founders", c.rules_fired)

    async def test_yes_and_no_are_flagged_by_confidence(self):
        self.assertTrue((await self.judge_founders("yes", 0.55)).signals[0].needs_review)
        self.assertFalse((await self.judge_founders("yes", 0.85)).signals[0].needs_review)
        self.assertTrue((await self.judge_founders("no", 0.6)).signals[0].needs_review)

    async def test_confident_yes_still_earns_the_same_points(self):
        c = await self.judge_founders("yes", 0.9)
        with patch.object(score, "now_utc", return_value=SimpleNamespace(date=lambda: date(2026, 9, 22))):
            score.score_company(c)
        self.assertIn("technical_founders", c.rules_fired)
        self.assertEqual(config.SCORING_WEIGHTS["technical_founders"], 10)


if __name__ == "__main__":
    unittest.main()
