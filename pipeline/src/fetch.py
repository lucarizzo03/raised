"""Async HTTP fetching and HTML-to-text extraction."""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from . import config

log = logging.getLogger(__name__)

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_STRIP_TAGS = ["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside"]


def html_to_text(html: str, limit: int = config.ARTICLE_TEXT_LIMIT) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()[:limit]


class Fetcher:
    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(config.HTTP_MAX_CONCURRENCY)
        self._client = httpx.AsyncClient(
            timeout=config.HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": BROWSER_UA},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get(self, url: str, **kwargs) -> httpx.Response | None:
        async with self._sem:
            try:
                resp = await self._client.get(url, **kwargs)
                if resp.status_code >= 400:
                    log.debug("GET %s -> %s", url, resp.status_code)
                    return None
                return resp
            except (httpx.HTTPError, asyncio.TimeoutError) as exc:
                log.debug("GET %s failed: %s", url, exc)
                return None

    async def get_text(self, url: str, **kwargs) -> str:
        resp = await self.get(url, **kwargs)
        if resp is None:
            return ""
        content_type = resp.headers.get("content-type", "")
        if "html" in content_type or "xml" in content_type or not content_type:
            return html_to_text(resp.text)
        return resp.text[: config.ARTICLE_TEXT_LIMIT]


def normalize_domain(raw: str | None) -> str | None:
    """lowercase, strip scheme/www/path/query. Returns None if unusable."""
    if not raw:
        return None
    raw = raw.strip().lower()
    if "://" not in raw:
        raw = "https://" + raw
    host = urlparse(raw).netloc or urlparse(raw).path.split("/")[0]
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def domain_stem(domain: str | None) -> str | None:
    """'acme.io' -> 'acme'"""
    if not domain:
        return None
    return domain.split(".")[0]
