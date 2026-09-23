import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src import config, extract, judge, jobs, main
from src.fetch import normalize_url
from src.models import Company, FeedItem, JobPosting

TODAY = date(2026, 9, 22)


def job(title, department=None):
    return JobPosting(title=title, url="https://jobs.example.com/" + title, board="ashby", department=department)


class JobPrefilterTests(unittest.IsolatedAsyncioTestCase):
    def test_sales_titles_and_departments_are_kept(self):
        kept = jobs.sales_candidates([
            job("Senior Account Executive, New Logo"), job("Founding AE"), job("SDR"),
            job("Head of Sales"), job("Business Development Representative (BDR)"),
            job("Chief Revenue Officer"), job("Partner Manager", "Go To Market"),
            job("Software Engineer"), job("Senior Accounting Manager"), job("Product Designer", "Design"),
            job("Aerospace Engineer"),  # 'ae' must be a whole word
        ])
        self.assertEqual([j.title for j in kept], [
            "Senior Account Executive, New Logo", "Founding AE", "SDR", "Head of Sales",
            "Business Development Representative (BDR)", "Chief Revenue Officer", "Partner Manager",
        ])

    def test_cap_prefers_title_matches(self):
        dept_only = [job(f"Ops {i}", "Sales") for i in range(config.MAX_JOBS_CLASSIFIED_PER_COMPANY)]
        titled = [job(f"Account Executive {i}") for i in range(5)]
        kept = jobs.sales_candidates(dept_only + titled)
        self.assertEqual(len(kept), config.MAX_JOBS_CLASSIFIED_PER_COMPANY)
        self.assertEqual(kept[:5], titled)

    async def test_only_candidates_are_sent_to_the_classifier(self):
        c = Company(name="Big Co", dedupe_key="big", source_url="",
                    jobs=[job("Software Engineer")] * 300 + [job("Account Executive")])
        with patch.object(judge, "judge_company", AsyncMock()), \
             patch.object(judge, "judge_job", AsyncMock()) as judge_job:
            await judge._judge_company_and_jobs(c)
        self.assertEqual([call.args[1].title for call in judge_job.await_args_list], ["Account Executive"])
        self.assertEqual(len(c.jobs), 301)  # "open roles" count is unchanged


class ProcessedArticleTests(unittest.IsolatedAsyncioTestCase):
    def test_url_normalization(self):
        self.assertEqual(normalize_url("HTTPS://www.TechCrunch.com/2026/09/acme/?utm_source=rss&id=7#top"),
                         "https://techcrunch.com/2026/09/acme?id=7")
        self.assertEqual(normalize_url("https://techcrunch.com/2026/09/acme"),
                         normalize_url("https://www.techcrunch.com/2026/09/acme/"))

    async def test_outcomes_are_recorded_and_failures_are_not(self):
        items = [FeedItem(title=n, url=f"https://news.example.com/{n}", published=TODAY, source="t", text="x")
                 for n in ("funding", "dupe", "opinion", "boom", "old")]
        items[-1].published = date(2020, 1, 1)
        unfetched = FeedItem(title="blocked", url="https://news.example.com/blocked", published=TODAY, source="t")
        replies = {"funding": {"company_name": "Acme"}, "dupe": {"company_name": "Acme"},
                   "opinion": {"not_funding_article": True}, "boom": RuntimeError("timeout")}

        async def complete_json(system, user, **kwargs):
            title = user.split("\n")[0].removeprefix("Article title: ")
            reply = replies[title]
            if isinstance(reply, Exception):
                raise reply
            return reply

        outcomes = {}
        with patch.object(extract.llm, "complete_json", complete_json), \
             patch.object(extract, "now_utc", return_value=SimpleNamespace(date=lambda: TODAY)), \
             patch.object(extract, "_fill_text", AsyncMock()), \
             patch.object(extract.domains, "pick_domain", return_value=(None, "none")):
            await extract.extract_companies(items + [unfetched], outcomes=outcomes)
        self.assertEqual(outcomes, {
            "https://news.example.com/funding": "company",
            "https://news.example.com/dupe": "duplicate",
            "https://news.example.com/opinion": "not_funding",
            "https://news.example.com/old": "out_of_window",
        })  # 'boom' (model failure) and 'blocked' (fetch failure) are retried next run

    async def test_known_articles_are_skipped_before_extraction(self):
        items = [FeedItem(title=n, url=f"https://www.news.example.com/{n}/", published=TODAY, source="t") for n in ("seen", "new")]
        with patch("src.feeds.fetch_all_feeds", AsyncMock(return_value=items)), \
             patch.object(main.db, "known_article_urls", return_value={"https://news.example.com/seen"}), \
             patch("src.extract.extract_companies", AsyncMock(return_value=[])) as extract_companies:
            await main._discover(False, 3, {})
        self.assertEqual([i.title for i in extract_companies.await_args.args[0]], ["new"])

    async def test_articles_of_failed_companies_are_not_marked_processed(self):
        ok = Company(name="Ok", dedupe_key="ok", source_url="https://n.example.com/ok", raised_date=TODAY,
                     article_published_at=TODAY, funding_evidence="a")
        bad = ok.model_copy(update={"name": "Bad", "dedupe_key": "bad", "source_url": "https://n.example.com/bad"})

        async def discover(mock, window, outcomes):
            outcomes.update({"https://n.example.com/ok": "company", "https://n.example.com/bad": "company",
                             "https://n.example.com/op-ed": "not_funding"})
            return [ok, bad]

        async def judge_all(companies):
            bad.failed_stage = "judge"

        with patch.object(main, "_discover", discover), \
             patch.object(main, "_dedupe_against_db", AsyncMock(side_effect=lambda c: c)), \
             patch.object(main.db, "migrate"), patch.object(main.db, "exclude_aged_out"), \
             patch.object(main.db, "dashboard_summary", return_value={}), \
             patch.object(main.db, "persist_run", return_value={}) as persist, \
             patch("src.judge.judge_new_round", AsyncMock()), patch("src.jobs.fetch_all_jobs", AsyncMock()), \
             patch("src.judge.judge_all", side_effect=judge_all), patch("src.investigate.investigate_all", AsyncMock()), \
             patch("src.judge.preflight", AsyncMock()), \
             patch("builtins.print"):
            await main.main(["run"])
        self.assertEqual(persist.call_args.kwargs["processed_articles"],
                         {"https://n.example.com/ok": "company", "https://n.example.com/op-ed": "not_funding"})
        self.assertEqual([c.name for c in persist.call_args.args[0]], ["Ok"])


if __name__ == "__main__":
    unittest.main()
