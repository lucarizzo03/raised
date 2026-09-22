"""LLM extraction: article text -> FundingExtraction."""

from __future__ import annotations

import asyncio
import logging

from pydantic import ValidationError

from . import llm
from .fetch import Fetcher, normalize_domain, normalize_name
from .models import Company, FeedItem, FundingExtraction, Round

log = logging.getLogger(__name__)

SYSTEM = """You extract funding events from news articles and SEC filings.
Given the article text, return JSON:
{
  "not_funding_article": false,
  "company_name": "Acme",
  "domain": "acme.com",
  "round": "pre_seed|seed|series_a|series_b|later|unknown",
  "amount_raised": 12000000,
  "raised_date": "2026-09-15",
  "investors": ["Sequoia", "a16z"]
}
Rules:
- If the article is not about a specific private company raising money
  (roundups, opinion, public companies, product news), return
  {"not_funding_article": true} and nothing else. Do not guess.
- amount_raised is a number in USD (no symbols). null if not stated.
- round must be one of the listed values. "unknown" if unstated.
- domain should be the company's real website, not the publisher's.
- raised_date is when the round was announced/closed, ISO format.
- If the article is an SEC Form D filing, company_name is the entity name;
  domain is usually absent (leave null); use the filing date as raised_date."""


async def extract_one(item: FeedItem) -> FundingExtraction | None:
    if not item.text:
        return None
    try:
        data = await llm.complete_json(
            SYSTEM, f"Article title: {item.title}\n\n{item.text}"
        )
    except Exception as exc:
        log.warning("extraction failed for %s: %s", item.url, exc)
        return None
    try:
        return FundingExtraction.model_validate(data)
    except ValidationError as exc:
        log.warning("bad extraction payload for %s: %s", item.url, exc)
        return None


async def extract_companies(items: list[FeedItem]) -> list[Company]:
    """Fetch article bodies, extract in parallel, dedupe, return Companies."""
    fetcher = Fetcher()
    try:
        await asyncio.gather(
            *(_fill_text(fetcher, item) for item in items if not item.text)
        )
        extractions = await asyncio.gather(*(extract_one(i) for i in items))
    finally:
        await fetcher.close()

    # Dedupe on domain AND normalized name: the extractor often guesses a
    # different TLD for the same company across articles (acme.com / acme.ai).
    seen_keys: set[str] = set()
    companies: list[Company] = []
    for item, ext in zip(items, extractions):
        if ext is None or ext.not_funding_article or not ext.company_name:
            continue
        domain = normalize_domain(ext.domain)
        name_key = normalize_name(ext.company_name)
        key = domain or name_key
        if not key or key in seen_keys or name_key in seen_keys:
            continue
        seen_keys.add(key)
        if name_key:
            seen_keys.add(name_key)
        companies.append(
            Company(
                name=ext.company_name.strip(),
                domain=domain,
                dedupe_key=key,
                round=ext.round if ext.round != Round.UNKNOWN else Round.UNKNOWN,
                amount_raised=ext.amount_raised,
                raised_date=ext.raised_date or item.published,
                investors=ext.investors,
                source_url=item.url,
                article_title=item.title,
            )
        )
    log.info("extracted %d funding events (deduped)", len(companies))
    return companies


async def _fill_text(fetcher: Fetcher, item: FeedItem) -> None:
    item.text = await fetcher.get_text(item.url)
