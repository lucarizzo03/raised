from __future__ import annotations

import asyncio
import json
import logging

from bs4 import BeautifulSoup

from . import config, dates, db, extract, judge
from .fetch import Fetcher, normalize_name
from .models import FeedItem

log = logging.getLogger(__name__)


async def audit_existing():
    companies = db.load_existing()
    fetcher = Fetcher()
    sem = asyncio.Semaphore(config.HTTP_MAX_CONCURRENCY)

    async def audit(company):
        async with sem:
            text, html = await fetcher.get_text_html(company.source_url) if company.source_url else ("", "")
            if text and html:
                soup = BeautifulSoup(html, "html.parser")
                company.article_title = soup.title.get_text(" ", strip=True) if soup.title else company.article_title
                company.article_published_at = dates.article_publication_date(html) or company.article_published_at
                item = FeedItem(title=company.article_title, url=company.source_url,
                                published=company.article_published_at, source="cleanup", text=text, html=html)
                result = await extract.extract_one(item)
                if result:
                    evidence = result.model_dump(mode="json")
                    evidence["previous_raised_date"] = str(company.raised_date) if company.raised_date else None
                    company.funding_evidence = json.dumps(evidence)
                    if (not result.not_funding_article and result.company_name
                        and normalize_name(result.company_name) == normalize_name(company.name)
                        and result.round == company.round and result.raised_date):
                        company.raised_date = result.raised_date
            await judge.judge_new_round(company)
            dates.apply_rejection(company)
            log.info("cleanup %s: %s", company.name, company.rejection_reason or "kept")

    try:
        await asyncio.gather(*(audit(company) for company in companies))
    finally:
        await fetcher.close()
    return companies
