import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from src import config, db, judge
from src.models import Company, Signal


def company(name, genuine="yes", startup="yes", confidence=0.9):
    today = date(2026, 9, 22)
    return Company(name=name, dedupe_key=name.lower(), source_url="", raised_date=today,
                   article_published_at=today, funding_evidence="announcement",
                   signals=[Signal(signal_type="genuine_raise", value=genuine, confidence=confidence),
                            Signal(signal_type="is_startup", value=startup, confidence=confidence)])


class GateTests(unittest.IsolatedAsyncioTestCase):
    async def judge(self, companies):
        with patch.object(judge, "judge_company", AsyncMock()):
            await judge.judge_all(companies)

    async def test_confident_no_is_rejected_and_excluded(self):
        bar = company("Bar", genuine="no")
        cos = [company("A"), company("B"), company("C"), bar]
        await self.judge(cos)
        self.assertEqual(bar.rejection_reason, "not_startup_raise")
        self.assertTrue(bar.excluded)
        self.assertIn("genuine_raise=no", bar.rejection_detail)
        self.assertEqual([c.name for c in cos if c.rejection_reason], ["Bar"])
        self.assertEqual(db._rejection_confidence(bar), 0.9)

    async def test_unconfident_no_is_kept_for_review(self):
        unsure = company("Unsure", startup="no", confidence=config.CONFIDENCE_REVIEW_THRESHOLD - 0.01)
        await self.judge([unsure])
        self.assertIsNone(unsure.rejection_reason)

    async def test_a_small_batch_is_still_enforced(self):
        bar = company("Bar", startup="no")
        await self.judge([bar])
        self.assertEqual(bar.rejection_reason, "not_startup_raise")

    async def test_mass_rejection_is_treated_as_a_model_problem(self):
        cos = [company(n, genuine="no") for n in "ABCD"] + [company("E")]
        await self.judge(cos)
        self.assertEqual([c for c in cos if c.rejection_reason], [])


if __name__ == "__main__":
    unittest.main()
