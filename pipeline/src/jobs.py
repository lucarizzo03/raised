"""Job board probing: guess the board slug from the domain, try Ashby,
Greenhouse, Lever public JSON APIs, take the first that responds."""

from __future__ import annotations

import asyncio
import logging
import re

from . import config
from .fetch import Fetcher, domain_stem, normalize_name
from .models import Company, JobPosting

log = logging.getLogger(__name__)

# Deliberately broad: this only decides which titles are worth a model call;
# the classifier still makes the sales / not-sales judgment.
_SALES_TITLE = re.compile(
    r"\b(sales|account executive|account exec|ae|sdr|bdr|adr|business development|"
    r"revenue|cro|go[- ]to[- ]market|gtm|commercial|partnerships?|"
    r"account (manager|director|lead)|seller|deal desk|pre-?sales)\b",
    re.IGNORECASE,
)
_SALES_DEPARTMENT = re.compile(r"\b(sales|revenue|go[- ]to[- ]market|gtm|business development)\b", re.IGNORECASE)


def sales_candidates(jobs: list[JobPosting]) -> list[JobPosting]:
    """Jobs worth classifying: sales-looking title or department, capped.

    Title matches rank ahead of department-only ones, so the cap keeps an
    "Account Executive" over a "Finance Director" filed under GTM.
    """
    by_title = [j for j in jobs if _SALES_TITLE.search(j.title or "")]
    title_ids = {id(j) for j in by_title}
    by_department = [j for j in jobs if id(j) not in title_ids and _SALES_DEPARTMENT.search(j.department or "")]
    return (by_title + by_department)[: config.MAX_JOBS_CLASSIFIED_PER_COMPANY]


def slug_candidates(company: Company) -> list[str]:
    candidates: list[str] = []
    stem = domain_stem(company.domain)
    if stem:
        candidates.append(stem)
        candidates.append(stem.replace("-", ""))
    name_key = normalize_name(company.name)
    if name_key:
        candidates.append(name_key)
        for suffix in ("inc", "labs", "hq", "ai", "app"):
            if name_key.endswith(suffix) and len(name_key) > len(suffix) + 2:
                candidates.append(name_key[: -len(suffix)])
    # dedupe, preserve order
    return list(dict.fromkeys(candidates))


async def _try_ashby(fetcher: Fetcher, slug: str) -> list[JobPosting] | None:
    resp = await fetcher.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    )
    if resp is None:
        return None
    try:
        jobs = resp.json().get("jobs", [])
    except ValueError:
        return None
    return [
        JobPosting(
            title=j.get("title", ""),
            url=j.get("jobUrl") or f"https://jobs.ashbyhq.com/{slug}/{j.get('id', '')}",
            board="ashby",
            department=(j.get("department") or {}).get("name")
            if isinstance(j.get("department"), dict)
            else j.get("department"),
            location=(j.get("location") or {}).get("name")
            if isinstance(j.get("location"), dict)
            else j.get("location"),
            description_text=j.get("descriptionPlain", "")[:4000],
        )
        for j in jobs
    ]


async def _try_greenhouse(fetcher: Fetcher, slug: str) -> list[JobPosting] | None:
    resp = await fetcher.get(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    )
    if resp is None:
        return None
    try:
        jobs = resp.json().get("jobs", [])
    except ValueError:
        return None
    return [
        JobPosting(
            title=j.get("title", ""),
            url=j.get("absolute_url", ""),
            board="greenhouse",
            department=(j.get("departments") or [{}])[0].get("name")
            if j.get("departments")
            else None,
            location=(j.get("location") or {}).get("name"),
            description_text=j.get("content", "")[:4000],
        )
        for j in jobs
    ]


async def _try_lever(fetcher: Fetcher, slug: str) -> list[JobPosting] | None:
    resp = await fetcher.get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if resp is None:
        return None
    try:
        jobs = resp.json()
    except ValueError:
        return None
    if not isinstance(jobs, list):
        return None
    return [
        JobPosting(
            title=j.get("text", ""),
            url=j.get("hostedUrl", ""),
            board="lever",
            department=(j.get("categories") or {}).get("team"),
            location=(j.get("categories") or {}).get("location"),
            description_text=(j.get("descriptionPlain") or "")[:4000],
        )
        for j in jobs
    ]


_BOARDS = [_try_ashby, _try_greenhouse, _try_lever]


async def fetch_jobs(company: Company, fetcher: Fetcher) -> list[JobPosting]:
    for slug in slug_candidates(company):
        for board in _BOARDS:
            try:
                jobs = await board(fetcher, slug)
            except Exception as exc:  # malformed board payload: try the next one
                log.warning("%s: %s failed for slug %s: %s", company.name, board.__name__, slug, exc)
                continue
            if jobs:
                log.info("%s: %d jobs on %s (slug=%s)", company.name, len(jobs), board.__name__, slug)
                return jobs
    return []


async def fetch_all_jobs(companies: list[Company]) -> None:
    fetcher = Fetcher()
    try:
        results = await asyncio.gather(*(fetch_jobs(c, fetcher) for c in companies))
    finally:
        await fetcher.close()
    for company, jobs in zip(companies, results, strict=True):
        company.jobs = jobs
