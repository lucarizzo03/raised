"""LLM extraction: article text -> FundingExtraction."""

from __future__ import annotations

import asyncio
import logging

from pydantic import ValidationError

from . import domains, llm
from .fetch import Fetcher, normalize_name
from .models import Company, FeedItem, FundingExtraction, Round, Signal

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
    """Fetch article bodies, extract, resolve + verify domains, dedupe."""
    fetcher = Fetcher()
    try:
        await asyncio.gather(
            *(_fill_text(fetcher, item) for item in items if not item.text)
        )
        extractions = await asyncio.gather(*(extract_one(i) for i in items))

        # Resolve a domain from the article itself. Never from the name.
        pending: list[tuple[FeedItem, FundingExtraction, str | None, str]] = []
        for item, ext in zip(items, extractions):
            if ext is None or ext.not_funding_article or not ext.company_name:
                continue
            domain, source = domains.pick_domain(
                name=ext.company_name,
                html=item.html,
                text=item.text,
                source_url=item.url,
                model_domain=ext.domain,
                investors=ext.investors,
            )
            pending.append((item, ext, domain, source))

        verified = await asyncio.gather(
            *(
                domains.verify(fetcher, d, e.company_name) if d else _false()
                for _, e, d, _s in pending
            )
        )
    finally:
        await fetcher.close()

    # Dedupe on a verified domain when we have one, otherwise the name. An
    # unverified domain is not identity - that is what collided companies
    # onto each other before.
    seen_keys: set[str] = set()
    companies: list[Company] = []
    for (item, ext, domain, source), ok in zip(pending, verified):
        name_key = normalize_name(ext.company_name)
        if domain and not ok:
            log.info("domain %s rejected for %s (unverified)", domain, ext.company_name)
            domain, source = None, f"{source}_unverified"
        key = domain if (domain and ok) else name_key
        if not key or key in seen_keys or name_key in seen_keys:
            continue
        seen_keys.add(key)
        if name_key:
            seen_keys.add(name_key)
        company = Company(
            name=ext.company_name.strip(),
            domain=domain,
            domain_verified=bool(domain and ok),
            domain_source=source,
            dedupe_key=key,
            round=ext.round,
            amount_raised=ext.amount_raised,
            raised_date=ext.raised_date or item.published,
            investors=ext.investors,
            source_url=item.url,
            article_title=item.title,
        )
        if not company.domain_verified:
            company.signals.append(
                Signal(
                    signal_type="domain_unverified",
                    value="Domain unverified",
                    confidence=0.0,
                    needs_review=True,
                    source_url=item.url,
                )
            )
        companies.append(company)
    n_ok = sum(1 for c in companies if c.domain_verified)
    log.info(
        "extracted %d funding events (deduped); %d verified domains, %d null",
        len(companies), n_ok, len(companies) - n_ok,
    )
    return companies


async def _false() -> bool:
    return False


async def _fill_text(fetcher: Fetcher, item: FeedItem) -> None:
    item.text, item.html = await fetcher.get_text_html(item.url)
