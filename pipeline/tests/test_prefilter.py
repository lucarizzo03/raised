import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src import extract, prefilter
from src.judge import Judgment
from src.models import FeedItem

TODAY = date(2026, 9, 22)


def item(title, n=0, source="google_news", text="article text"):
    return FeedItem(title=title, url=f"https://news{n}.example.com/{abs(hash(title))}", published=TODAY,
                    source=source, text=text)


class HeadlineTests(unittest.TestCase):
    def test_company_names_from_real_headlines(self):
        cases = {
            "Armadin Raises $255.5 Million Series B to Scale Autonomous Security - PR Newswire": "armadin",
            "Exclusive | AI Cyber Startup Armadin Raises $255 Million - WSJ": "armadin",
            "London's Metaview raises €53.1 million Series C led by Insight Partners - EU-Startups": "metaview",
            "a16z-backed EliseAI raises $350M, doubles valuation to $4B": "eliseai",
            "Exclusive: Hop Aero Raises $11M for Suborbital Point-to-Point Delivery - payloadspace.com": "hopaero",
            "Unveilr AI secures pre-seed funding at Rs 16.7 cr valuation - SaasRise": "unveilrai",
            "doxx.net raises $38M Series A led by Andreessen Horowitz - SaasRise": "doxxnet",
            "Parakeet Health Raises $10 Million Series A - Pulse 2.0": "parakeethealth",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(prefilter.headline_company(title), expected)

    def test_headlines_without_the_pattern_are_left_alone(self):
        for title in [
            "AI cybersecurity startup Armadin valued at over $2.5 billion after new funding round - Reuters",
            "Funding Tracker '26: Ours Privacy, Arintra and Happy Health - fiercehealthcare.com",
            "3 days left to exhibit at TechCrunch Disrupt 2026",
        ]:
            with self.subTest(title=title):
                self.assertIsNone(prefilter.headline_company(title))


class GroupingTests(unittest.TestCase):
    def test_one_article_per_raise(self):
        a = [item("Armadin Raises $255M Series B - PR Newswire", 1),
             item("Exclusive | AI Cyber Startup Armadin Raises $255 Million - WSJ", 2),
             item("Palo Alto's Armadin raises $255.5M - Hoodline", 3)]
        other = item("Hestus raises $7.4M seed - Dealroom", 4)
        loose = item("Funding Tracker '26: Ours Privacy and Arintra", 5)
        reps, dupes, known = prefilter.group(a + [other, loose])
        self.assertEqual(len(reps), 3)
        self.assertIn(loose, reps)  # no name -> its own group
        rep = next(r for r in reps if r in a)
        self.assertEqual(len(dupes[id(rep)]), 2)
        self.assertEqual(known, [])

    def test_prefers_an_article_that_fetched_then_techcrunch(self):
        paywalled = item("Armadin raises $255M - WSJ", 1, text="")
        news = item("Armadin raises $255M - Hoodline", 2)
        tc = item("Armadin raises $255M", 3, source="techcrunch")
        reps, _, _ = prefilter.group([paywalled, news, tc])
        self.assertEqual(reps, [tc])
        reps, _, _ = prefilter.group([paywalled, news])
        self.assertEqual(reps, [news])

    def test_longer_descriptor_merges_into_the_short_name(self):
        a = item("Seeds Fincap Raises Rs 100 Crore Series B - siliconindia", 1)
        b = item("NBFC Company Seeds Fincap Raises Rs 100 Cr In Series B - Inc42", 2)
        c = item("Flow raises $50m in Series B - dev", 3)
        d = item("Flow Engineering Raises $50M Series B - Hoodline", 4)  # "flow" is too short to merge on
        reps, _, _ = prefilter.group([a, b, c, d])
        self.assertEqual(len(reps), 3)

    def test_known_companies_are_set_aside(self):
        reps, _, known = prefilter.group([item("Armadin raises $255M", 1), item("Hestus raises $7M", 2)], known={"armadin"})
        self.assertEqual([r.title for r in reps], ["Hestus raises $7M"])
        self.assertEqual([k.title for k in known], ["Armadin raises $255M"])


class ScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_a_confident_no_is_skipped(self):
        answers = {"late": Judgment("no", 0.93), "unsure": Judgment("no", 0.6), "early": Judgment("yes", 0.9)}
        items = [item(t, i) for i, t in enumerate(answers)]

        async def ask(state, questions):
            if "headline: broken" in state:
                raise RuntimeError("bad payload")
            return {"early_raise": answers[state.split("\n")[0].removeprefix("headline: ")]}

        backend = SimpleNamespace(ask=ask)
        with patch("src.judge.backend", return_value=backend), patch("src.judge._questions", return_value={}):
            skipped = await prefilter.screen(items)
            self.assertEqual(skipped, {id(items[0]): 0.93})
            # A failed call keeps the article for Claude.
            broken = [item("broken", 9)] + [item("early", 10 + i) for i in range(4)]
            self.assertEqual(await prefilter.screen(broken), {})


class ExtractionWiringTests(unittest.IsolatedAsyncioTestCase):
    async def run_extract(self, items, replies, skipped=None):
        async def complete_json(system, user, **kwargs):
            reply = replies[user.split("\n")[0].removeprefix("Article title: ")]
            if isinstance(reply, Exception):
                raise reply
            return reply

        async def screen(reps):
            return {id(r): 0.9 for r in reps if r.title in (skipped or ())}

        outcomes = {}
        claude = AsyncMock(side_effect=complete_json)
        with patch.object(extract.llm, "complete_json", claude), \
             patch.object(extract, "now_utc", return_value=SimpleNamespace(date=lambda: TODAY)), \
             patch.object(extract.prefilter, "screen", screen), \
             patch.object(extract, "_fill_text", AsyncMock()), \
             patch.object(extract.domains, "pick_domain", return_value=(None, "none")):
            companies = await extract.extract_companies(items, outcomes=outcomes, known_names={"oldco"})
        return companies, outcomes, claude

    async def test_duplicates_and_skips_never_reach_claude(self):
        armadin = [item("Armadin raises $255M Series B", i, source="techcrunch" if i == 0 else "google_news") for i in range(3)]
        late = [item("PaleBlueDot AI raises $200M Series C", 10 + i) for i in range(2)]
        known = item("OldCo raises $5M seed", 20)
        replies = {"Armadin raises $255M Series B": {"company_name": "Armadin", "round": "series_b"}}
        companies, outcomes, claude = await self.run_extract(
            armadin + late + [known], replies, skipped={"PaleBlueDot AI raises $200M Series C"})
        self.assertEqual(claude.await_count, 1)
        self.assertEqual([c.name for c in companies], ["Armadin"])
        self.assertEqual(outcomes[extract.normalize_url(armadin[0].url)], "company")
        self.assertEqual({outcomes[extract.normalize_url(a.url)] for a in armadin[1:]}, {"duplicate"})
        self.assertEqual({outcomes[extract.normalize_url(p.url)] for p in late},
                         {("prefilter_skipped", "jev confidence 0.90")})
        self.assertEqual(outcomes[extract.normalize_url(known.url)], "known_company")

    async def test_duplicates_are_retried_when_their_article_fails(self):
        articles = [item("Hestus raises $7.4M seed", i) for i in range(5)]
        others = [item(f"Co{i} raises $1M seed", 10 + i) for i in range(4)]
        replies = {"Hestus raises $7.4M seed": RuntimeError("timeout"),
                   **{o.title: {"company_name": o.title.split()[0]} for o in others}}
        _, outcomes, _ = await self.run_extract(articles + others, replies)
        self.assertFalse(any(extract.normalize_url(a.url) in outcomes for a in articles))


if __name__ == "__main__":
    unittest.main()
