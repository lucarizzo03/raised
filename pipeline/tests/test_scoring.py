import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from src import config, score
from src.models import Company, Round, Signal

TODAY = date(2026, 9, 22)


def company(round=Round.SEED, age=0, signals=(), amount=None, name="Acme") -> Company:
    return Company(name=name, dedupe_key=name.lower(), source_url="", round=round,
                   raised_date=TODAY - timedelta(days=age), amount_raised=amount,
                   signals=[Signal(signal_type=t, value=v, confidence=c) for t, v, c in signals])


class ScoringTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(score, "now_utc", return_value=datetime(2026, 9, 22, 23, 30, tzinfo=timezone.utc))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_days_are_counted_in_utc(self):
        with patch.object(score, "now_utc", return_value=datetime(2026, 9, 23, 1, 0, tzinfo=timezone.utc)):
            # 01:00 UTC is still the 22nd in US time zones; UTC decides.
            self.assertEqual(score._days_since_raise(company(age=0)), 1)

    def test_maximum_score_is_120(self):
        c = company(signals=[
            ("sales_role", "yes (Account Executive)", 0.9),
            ("first_sales_hire", "yes", 0.9),
            ("technical_founders", "yes", 0.9),
            ("icp_fit", "4", 0.9),
        ])
        score.score_company(c)
        self.assertEqual(c.score, 120)
        self.assertEqual(c.rules_fired, ["raise_recency (+30)", "round_seed_to_b", "first_sales_hire",
                                         "any_sales_role_open", "technical_founders", "icp_fit (+20)"])

    def test_first_sales_hire_needs_an_open_sales_role(self):
        c = company(age=config.RECENCY_WINDOW_DAYS, round=Round.LATER, signals=[("first_sales_hire", "yes", 0.9)])
        score.score_company(c)
        self.assertEqual(c.score, 0)
        self.assertEqual(c.explanation, "Raised later 90d ago.")

    def test_recency_ramp(self):
        self.assertEqual(score.recency_points(company(age=0)), 30)
        self.assertEqual(score.recency_points(company(age=45)), 15)
        self.assertEqual(score.recency_points(company(age=90)), 0)
        self.assertEqual(score.recency_points(company(age=-1)), 0)  # future-dated

    def test_icp_points_are_clamped_and_tolerate_garbage(self):
        self.assertEqual(score.icp_points(company(signals=[("icp_fit", "2", 0.9)]))[0], 10)
        self.assertEqual(score.icp_points(company(signals=[("icp_fit", "9", 0.9)]))[0], 20)
        self.assertEqual(score.icp_points(company(signals=[("icp_fit", "-3", 0.9)]))[0], 0)
        self.assertEqual(score.icp_points(company(signals=[("icp_fit", "None", 0.9)]))[0], 0)

    def test_latest_icp_judgment_wins(self):
        c = company(signals=[("icp_fit", "0", 0.9), ("icp_fit", "4", 0.9)])
        self.assertEqual(score.icp_points(c)[0], 20)

    def test_exclusions(self):
        confident_b2c = company(signals=[("sells_to", "B2C", config.B2C_EXCLUDE_CONFIDENCE)])
        unsure_b2c = company(signals=[("sells_to", "B2C", config.B2C_EXCLUDE_CONFIDENCE - 0.01)])
        late_big = company(round=Round.LATER, amount=config.LATE_STAGE_AMOUNT_CEILING + 1)
        late_small = company(round=Round.LATER, amount=config.LATE_STAGE_AMOUNT_CEILING)
        self.assertIsNotNone(score.exclusion_reason(confident_b2c))
        self.assertIsNone(score.exclusion_reason(unsure_b2c))
        self.assertIsNotNone(score.exclusion_reason(late_big))
        self.assertIsNone(score.exclusion_reason(late_small))

    def test_rank_orders_and_hides_excluded(self):
        high = company(name="High", signals=[("sales_role", "yes", 0.9)])
        older = company(name="Older", age=10, signals=[("sales_role", "yes", 0.9)])
        tie_new = company(name="TieNew", age=10, signals=[("sales_role", "yes", 0.95)])
        b2c = company(name="Consumer", signals=[("sells_to", "B2C", 0.9)])
        ranked = score.rank([older, b2c, high, tie_new])
        self.assertEqual([c.name for c in ranked], ["High", "TieNew", "Older"])
        self.assertTrue(b2c.excluded)


if __name__ == "__main__":
    unittest.main()
