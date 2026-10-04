"""Feed pullers: TechCrunch RSS and Google News RSS."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import feedparser

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


async def fetch_all_feeds(window_days: int = config.INGEST_WINDOW_DAYS) -> list[FeedItem]:
    results = await asyncio.gather(
        fetch_techcrunch(window_days), fetch_google_news(window_days)
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
