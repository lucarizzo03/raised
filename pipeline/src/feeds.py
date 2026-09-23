"""Feed pullers: TechCrunch RSS, Google News RSS, SEC EDGAR Form D full-text search."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import feedparser
import httpx

from . import config
from .dates import now_utc
from .models import FeedItem

log = logging.getLogger(__name__)


def _entry_date(entry) -> datetime | None:
    parsed = entry.get("published_parsed")
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _filter_entries(entries, source: str, window_days: int) -> list[FeedItem]:
    now = now_utc()
    cutoff = now - timedelta(days=window_days)
    old = missing = future = 0
    items = []
    for entry in entries:
        published = _entry_date(entry)
        if published is None:
            missing += 1
        elif published < cutoff:
            old += 1
        elif published > now:
            future += 1
        elif entry.get("link"):
            items.append(FeedItem(title=entry.get("title", ""), url=entry["link"], published=published.date(), source=source))
    log.info("%s: fetched=%d skipped_too_old=%d skipped_missing_date=%d skipped_future=%d kept=%d window_days=%d", source, len(entries), old, missing, future, len(items), window_days)
    return items


async def fetch_techcrunch(window_days: int = config.INGEST_WINDOW_DAYS) -> list[FeedItem]:
    entries = []
    for url in config.TECHCRUNCH_FEEDS:
        feed = await asyncio.to_thread(feedparser.parse, url)
        entries.extend(feed.entries)
    return _filter_entries(entries, "techcrunch", window_days)


async def _resolve_google_news_urls(items: list[FeedItem]) -> None:
    """Google News RSS links are JS-redirect pages; decode via batchexecute."""
    from googlenewsdecoder import gnews_decoder_async

    if not items:
        return
    try:
        results = await gnews_decoder_async([i.url for i in items])
    except Exception as exc:
        log.warning("google news decode failed: %s", exc)
        return
    for item, result in zip(items, results, strict=False):
        decoded = (result or {}).get("decoded_url")
        if decoded:
            item.url = decoded


async def fetch_google_news(window_days: int = config.INGEST_WINDOW_DAYS) -> list[FeedItem]:
    entries = []
    for query in config.GOOGLE_NEWS_QUERIES:
        url = config.GOOGLE_NEWS_RSS.format(query=quote(query), window_days=window_days)
        feed = await asyncio.to_thread(feedparser.parse, url)
        entries.extend(feed.entries)
    items = list({i.url: i for i in _filter_entries(entries, "google_news", window_days)}.values())
    await _resolve_google_news_urls(items)
    return items


async def fetch_edgar(window_days: int = config.INGEST_WINDOW_DAYS) -> list[FeedItem]:
    end = now_utc().date()
    start = end - timedelta(days=window_days)
    params = {
        "q": '"funding" OR "offering"',
        "forms": config.EDGAR_FORMS,
        "dateRange": "custom",
        "startdt": start.isoformat(),
        "enddt": end.isoformat(),
    }
    items: list[FeedItem] = []
    old = missing = future = 0
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
            log.info("sec_edgar: fetched=0 skipped_too_old=0 skipped_missing_date=0 window_days=%d", window_days)
            return items
        for hit in hits:
            src = hit.get("_source", {})
            hit_id = hit.get("_id", "")
            name = src.get("entity_name") or src.get("display_names") or ""
            name = ", ".join(name) if isinstance(name, list) else name.strip()
            filed = src.get("file_date")
            ciks = src.get("ciks") or []
            try:
                filed_date = date.fromisoformat(filed) if filed else None
            except (ValueError, TypeError):
                filed_date = None
            if filed_date is None:
                missing += 1
                continue
            if filed_date < start:
                old += 1
                continue
            if filed_date > end:
                future += 1
                continue
            if ":" not in hit_id or not ciks:
                continue
            adsh, filename = hit_id.split(":", 1)
            url = f"https://www.sec.gov/Archives/edgar/data/{ciks[0]}/{adsh.replace('-', '')}/{filename}"
            items.append(FeedItem(title=f"Form D filing: {name}" if name else "Form D filing", url=url, published=filed_date, source="sec_edgar"))
    log.info("sec_edgar: fetched=%d skipped_too_old=%d skipped_missing_date=%d skipped_future=%d kept=%d window_days=%d", len(hits), old, missing, future, len(items), window_days)
    return items


async def fetch_all_feeds(window_days: int = config.INGEST_WINDOW_DAYS) -> list[FeedItem]:
    results = await asyncio.gather(
        fetch_techcrunch(window_days), fetch_google_news(window_days), fetch_edgar(window_days)
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
