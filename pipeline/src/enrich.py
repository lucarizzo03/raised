"""Everything judging needs beyond the article: job boards and the about page,
fetched together for each company with one HTTP client. No model calls."""

from __future__ import annotations

import asyncio

from . import jobs
from .fetch import Fetcher
from .models import Company


async def fetch_about(company: Company, fetcher: Fetcher) -> None:
    if not company.domain:
        company.about_text = "(no domain)"
        return
    for path in ("/about", "/team", "/about-us", "/company"):
        text = await fetcher.get_text(f"https://{company.domain}{path}")
        if text:
            company.about_text = text[:4000]
            return
    company.about_text = "(about page not found)"


async def _enrich(company: Company, fetcher: Fetcher) -> None:
    company.jobs, _ = await asyncio.gather(jobs.fetch_jobs(company, fetcher), fetch_about(company, fetcher))


async def enrich_all(companies: list[Company]) -> None:
    fetcher = Fetcher()
    try:
        await asyncio.gather(*(_enrich(c, fetcher) for c in companies))
    finally:
        await fetcher.close()
