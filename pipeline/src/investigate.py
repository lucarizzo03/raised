"""Investigation loop: Jev decides "score now or dig deeper?", picks one
action (careers page / recent news / about page), re-evaluates. Max 3 rounds.
Every decision is logged to company.decisions and persisted."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

import feedparser

from . import config
from .fetch import Fetcher
from .judge import decide_investigation, judge_company, judge_founders
from .models import Company

log = logging.getLogger(__name__)


async def _check_careers(company: Company, fetcher: Fetcher) -> None:
    if not company.domain:
        company.careers_text = "(no domain)"
        return
    for path in ("/careers", "/jobs"):
        text = await fetcher.get_text(f"https://{company.domain}{path}")
        if text:
            company.careers_text = text[:3000]
            return
    company.careers_text = "(careers page not found)"


async def _fetch_about(company: Company, fetcher: Fetcher) -> None:
    if not company.domain:
        company.about_text = "(no domain)"
        return
    for path in ("/about", "/team", "/about-us", "/company"):
        text = await fetcher.get_text(f"https://{company.domain}{path}")
        if text:
            company.about_text = text[:4000]
            return
    company.about_text = "(about page not found)"


async def _search_news(company: Company) -> None:
    query = quote(f'"{company.name}" funding OR hiring')
    url = (
        f"https://news.google.com/rss/search?q={query}%20when%3A90d"
        "&hl=en-US&gl=US&ceid=US:en"
    )
    feed = await asyncio.to_thread(feedparser.parse, url)
    company.news_snippets = [
        e.get("title", "") for e in feed.entries[:6] if e.get("title")
    ] or ["(no recent news found)"]


async def _run_action(company: Company, action: str, fetcher: Fetcher) -> None:
    if action == "check_careers":
        await _check_careers(company, fetcher)
    elif action == "fetch_about":
        await _fetch_about(company, fetcher)
    elif action == "search_news":
        await _search_news(company)


async def investigate_company(company: Company, fetcher: Fetcher) -> None:
    # Seed the about page up front when cheap - founder/first-hire judgments
    # need it, and the loop can still spend rounds on careers/news.
    if not company.about_text:
        await _fetch_about(company, fetcher)

    for round_num in range(1, config.MAX_INVESTIGATION_ROUNDS + 1):
        decision = await decide_investigation(company, round_num)
        log.info(
            "%s round %d: %s (conf %.2f)",
            company.name, round_num, decision.answer, decision.confidence,
        )
        if decision.answer == "score_now" or not decision.action_chosen:
            return
        await _run_action(company, decision.action_chosen, fetcher)
        await judge_company(company)  # re-evaluate with new evidence

    # Out of rounds - record the forced stop.
    decision = await decide_investigation(company, config.MAX_INVESTIGATION_ROUNDS + 1)
    decision.answer = "score_now"
    decision.action_chosen = None


async def investigate_all(companies: list[Company]) -> None:
    fetcher = Fetcher()
    try:
        await asyncio.gather(*(investigate_company(c, fetcher) for c in companies))
    finally:
        await fetcher.close()
    # Founder/first-hire judgments run after enrichment so they see about text.
    await asyncio.gather(*(judge_founders(c) for c in companies))
