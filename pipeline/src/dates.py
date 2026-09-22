from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from . import config
from .models import Company


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def date_violation(raised_date: date | None, article_date: date | None, today: date | None = None) -> str | None:
    today = today or now_utc().date()
    if raised_date is None:
        return None
    if raised_date > today:
        return "future_dated"
    if raised_date < today - timedelta(days=config.DISPLAY_WINDOW_DAYS):
        return "outside_display_window"
    if article_date and raised_date < article_date - timedelta(days=config.MAX_ARTICLE_LAG_DAYS):
        return "article_lag"
    return None


def apply_rejection(company: Company, today: date | None = None) -> None:
    today = today or now_utc().date()
    reason = detail = None
    violation = date_violation(company.raised_date, company.article_published_at, today)
    new_round = next((s for s in reversed(company.signals) if s.signal_type == "new_round"), None)
    if violation:
        reason, detail = "stale", violation
    elif new_round and new_round.value.lower() in {"no", "false"} and not new_round.needs_review and new_round.confidence >= config.CONFIDENCE_REVIEW_THRESHOLD:
        reason, detail = "not_new_round", "article does not announce this company's claimed round"
    elif not company.article_published_at or not company.raised_date or not company.funding_evidence:
        reason, detail = "source_unverifiable", "original announcement or publication date could not be verified"
    elif company.article_published_at > today:
        reason, detail = "source_unverifiable", "article publication date is in the future"
    company.rejection_reason, company.rejection_detail = reason, detail
    if reason:
        company.excluded, company.excluded_reason = True, reason
    elif company.excluded_reason in {"stale", "not_new_round", "source_unverifiable"}:
        company.excluded, company.excluded_reason = False, None


def _parse_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).date()
    except (ValueError, TypeError, OverflowError):
        pass
    for fmt in ("%B %d, %Y", "%B %d %Y", "%d %B %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def article_publication_date(html: str) -> date | None:
    soup = BeautifulSoup(html, "html.parser")
    for meta in soup.find_all("meta"):
        label = (meta.get("property") or meta.get("name") or meta.get("itemprop") or "").lower()
        if label in {"article:published_time", "og:published_time", "datepublished", "pubdate", "publishdate", "publish-date", "publication_date", "sailthru.date", "dc.date.issued", "date"}:
            parsed = _parse_date(meta.get("content"))
            if parsed:
                return parsed

    def published(value):
        if isinstance(value, dict):
            types = value.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if any(t in {"Article", "NewsArticle", "BlogPosting", "Report", "PressRelease"} for t in types):
                parsed = _parse_date(value.get("datePublished"))
                if parsed:
                    return parsed
            for child in value.values():
                result = published(child)
                if result:
                    return result
        elif isinstance(value, list):
            for child in value:
                result = published(child)
                if result:
                    return result
        return None

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            result = published(json.loads(script.string or script.get_text()))
            if result:
                return result
        except (ValueError, TypeError):
            pass
    for element in soup.select('[itemprop="datePublished"]'):
        parsed = _parse_date(element.get("datetime") or element.get("content") or element.get_text(" ", strip=True))
        if parsed:
            return parsed
    match = re.search(r"Published(?:\s+on)?\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})", soup.get_text(" ", strip=True), re.IGNORECASE)
    return _parse_date(match[1]) if match else None
