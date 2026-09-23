import unittest
from unittest.mock import AsyncMock, patch

from src import config, investigate, jobs
from src.models import Company, Decision, JobPosting


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


class InvestigationTests(unittest.IsolatedAsyncioTestCase):
    def decision(self, action, round_num):
        return Decision(question="q", answer=action, confidence=0.9,
                        action_chosen=None if action == "score_now" else action, round=round_num)

    async def test_stops_when_jev_says_score_now(self):
        c = company()
        c.about_text = "about"
        decide = AsyncMock(side_effect=lambda co, n: self.decision("score_now", n))
        with patch.object(investigate, "decide_investigation", decide), \
             patch.object(investigate, "judge_company", AsyncMock()) as rejudge:
            await investigate.investigate_company(c, fetcher=None)
        self.assertEqual(decide.await_count, 1)
        rejudge.assert_not_awaited()

    async def test_round_budget_is_enforced(self):
        c = company()
        c.about_text = "about"
        decide = AsyncMock(side_effect=lambda co, n: self.decision("search_news", n))
        with patch.object(investigate, "decide_investigation", decide), \
             patch.object(investigate, "_run_action", AsyncMock()) as action, \
             patch.object(investigate, "judge_company", AsyncMock()) as rejudge:
            await investigate.investigate_company(c, fetcher=None)
        self.assertEqual(action.await_count, config.MAX_INVESTIGATION_ROUNDS)
        self.assertEqual(rejudge.await_count, config.MAX_INVESTIGATION_ROUNDS)
        # One extra decision is logged for the forced stop.
        self.assertEqual(decide.await_count, config.MAX_INVESTIGATION_ROUNDS + 1)

    async def test_no_domain_means_no_requests(self):
        c = company(domain=None)
        await investigate._fetch_about(c, fetcher=None)
        await investigate._check_careers(c, fetcher=None)
        self.assertEqual((c.about_text, c.careers_text), ("(no domain)", "(no domain)"))


if __name__ == "__main__":
    unittest.main()
