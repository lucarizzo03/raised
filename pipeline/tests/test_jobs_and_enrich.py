import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src import enrich, jobs, judge
from src.judge import Judgment
from src.models import Company, JobPosting


def company(name="Acme Labs", domain="acme-labs.io") -> Company:
    return Company(name=name, domain=domain, dedupe_key=domain or name, source_url="")


class JobBoardTests(unittest.IsolatedAsyncioTestCase):
    def test_slug_candidates(self):
        self.assertEqual(jobs.slug_candidates(company()), ["acme-labs", "acmelabs", "acme"])
        self.assertEqual(jobs.slug_candidates(company("Beta AI", None)), ["betaai", "beta"])

    async def test_first_board_with_jobs_wins(self):
        posting = JobPosting(title="AE", url="https://jobs.lever.co/acme/1", board="lever")
        ashby = AsyncMock(return_value=None)
        greenhouse = AsyncMock(return_value=[])
        lever = AsyncMock(return_value=[posting])
        with patch.object(jobs, "_BOARDS", [ashby, greenhouse, lever]):
            result = await jobs.fetch_jobs(company(), fetcher=None)
        self.assertEqual(result, [posting])
        self.assertEqual(ashby.await_args.args[1], "acme-labs")

    async def test_a_malformed_board_does_not_drop_the_company(self):
        posting = JobPosting(title="AE", url="u", board="greenhouse")
        broken = AsyncMock(side_effect=ValueError("bad payload"))
        working = AsyncMock(return_value=[posting])
        with patch.object(jobs, "_BOARDS", [broken, working]):
            self.assertEqual(await jobs.fetch_jobs(company(), fetcher=None), [posting])


class EnrichTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_domain_means_no_requests(self):
        c = company(domain=None)
        await enrich.fetch_about(c, fetcher=None)
        self.assertEqual(c.about_text, "(no domain)")

    async def test_jobs_and_about_page_are_fetched_together(self):
        posting = JobPosting(title="AE", url="u", board="ashby")
        fetcher = SimpleNamespace(get_text=AsyncMock(return_value="Founded by two engineers."))
        c = company()
        with patch.object(jobs, "fetch_jobs", AsyncMock(return_value=[posting])):
            await enrich._enrich(c, fetcher)
        self.assertEqual(c.jobs, [posting])
        self.assertEqual(c.about_text, "Founded by two engineers.")


class OneCompanyCallTests(unittest.IsolatedAsyncioTestCase):
    async def test_jobs_are_judged_before_one_company_call_with_founders(self):
        c = company()
        c.about_text = "Founded by two ex-Stripe engineers."
        c.jobs = [JobPosting(title="Account Executive", url="https://jobs.example.com/1", board="ashby")]
        calls = []

        async def ask(state, questions):
            calls.append((state, set(questions)))
            if "is_sales" in questions:
                return {"is_sales": Judgment("yes", 0.9), "sales_type": Judgment("AE", 0.9)}
            answers = {"genuine_raise": Judgment("yes", 0.9), "is_startup": Judgment("yes", 0.9),
                       "sells_to": Judgment("B2B", 0.9), "round": Judgment("Seed", 0.9), "icp_fit": Judgment("4", 0.9)}
            return answers | {"technical_founders": Judgment("yes", 0.9), "first_sales_hire": Judgment("yes", 0.8)}

        with patch.object(judge, "backend", return_value=SimpleNamespace(ask=ask)), \
             patch.object(judge, "_questions", side_effect=lambda **q: q):
            await judge.judge_all([c])
        self.assertEqual(len(calls), 2)  # one job, then one company call
        state, questions = calls[1]
        self.assertTrue({"genuine_raise", "icp_fit", "technical_founders", "first_sales_hire"} <= questions)
        self.assertIn("open sales roles: Account Executive", state)
        self.assertIn("Founded by two ex-Stripe engineers.", state)
        self.assertEqual({s.signal_type for s in c.signals} & {"technical_founders", "first_sales_hire"},
                         {"technical_founders", "first_sales_hire"})


if __name__ == "__main__":
    unittest.main()
