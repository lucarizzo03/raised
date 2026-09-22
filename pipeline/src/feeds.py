"""Feed pullers: TechCrunch RSS, Google News RSS, SEC EDGAR Form D full-text search."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from urllib.parse import quote

import feedparser
import httpx

from . import config
from .models import FeedItem

log = logging.getLogger(__name__)


def _entry_date(entry) -> date | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return date(*parsed[:3])
    return None


async def fetch_techcrunch() -> list[FeedItem]:
    items: list[FeedItem] = []
    for url in config.TECHCRUNCH_FEEDS:
        feed = await asyncio.to_thread(feedparser.parse, url)
        for entry in feed.entries:
            items.append(
                FeedItem(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    published=_entry_date(entry),
                    source="techcrunch",
                )
            )
    log.info("techcrunch: %d items", len(items))
    return items


async def _resolve_google_news_urls(items: list[FeedItem]) -> None:
    """Google News RSS links are JS-redirect pages; decode via batchexecute."""
    from googlenewsdecoder import gnews_decoder_async

    try:
        results = await gnews_decoder_async([i.url for i in items])
    except Exception as exc:
        log.warning("google news decode failed: %s", exc)
        return
    for item, result in zip(items, results):
        decoded = (result or {}).get("decoded_url")
        if decoded:
            item.url = decoded


async def fetch_google_news() -> list[FeedItem]:
    items: list[FeedItem] = []
    seen: set[str] = set()
    for query in config.GOOGLE_NEWS_QUERIES:
        url = config.GOOGLE_NEWS_RSS.format(query=quote(query))
        feed = await asyncio.to_thread(feedparser.parse, url)
        for entry in feed.entries:
            link = entry.get("link", "")
            if not link or link in seen:
                continue
            seen.add(link)
            items.append(
                FeedItem(
                    title=entry.get("title", ""),
                    url=link,
                    published=_entry_date(entry),
                    source="google_news",
                )
            )
    log.info("google_news: %d items (resolving urls)", len(items))
    await _resolve_google_news_urls(items)
    return items


async def fetch_edgar() -> list[FeedItem]:
    end = date.today()
    start = end - timedelta(days=config.EDGAR_LOOKBACK_DAYS)
    params = {
        "q": '"funding" OR "offering"',
        "forms": config.EDGAR_FORMS,
        "dateRange": "custom",
        "startdt": start.isoformat(),
        "enddt": end.isoformat(),
    }
    items: list[FeedItem] = []
    async with httpx.AsyncClient(
        headers={"User-Agent": config.EDGAR_USER_AGENT},
        timeout=config.HTTP_TIMEOUT,
    ) as client:
        try:
            resp = await client.get(config.EDGAR_FULL_TEXT_SEARCH, params=params)
            resp.raise_for_status()
            hits = resp.json().get("hits", {}).get("hits", [])
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("edgar search failed: %s", exc)
            return items
        for hit in hits:
            src = hit.get("_source", {})
            hit_id = hit.get("_id", "")
            name = (src.get("entity_name") or "").strip()
            filed = src.get("file_date")
            ciks = src.get("ciks") or []
            url = ""
            if ":" in hit_id and ciks:
                adsh, filename = hit_id.split(":", 1)
                url = (
                    f"https://www.sec.gov/Archives/edgar/data/{ciks[0]}"
                    f"/{adsh.replace('-', '')}/{filename}"
                )
            filed_date = None
            if filed:
                try:
                    filed_date = datetime.strptime(filed, "%Y-%m-%d").date()
                except ValueError:
                    pass
            items.append(
                FeedItem(
                    title=f"Form D filing: {name}" if name else "Form D filing",
                    url=url or "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=D",
                    published=filed_date,
                    source="sec_edgar",
                    text=f"SEC Form D notice of exempt offering of securities filed by {name}.",
                )
            )
    log.info("sec_edgar: %d items", len(items))
    return items


async def fetch_all_feeds() -> list[FeedItem]:
    results = await asyncio.gather(
        fetch_techcrunch(), fetch_google_news(), fetch_edgar()
    )
    items = [item for sublist in results for item in sublist]
    # In-run dedupe on URL before we spend fetch calls on them.
    seen: set[str] = set()
    unique: list[FeedItem] = []
    for item in items:
        if item.url and item.url not in seen:
            seen.add(item.url)
            unique.append(item)
    log.info("feeds: %d unique items", len(unique))
    return unique
