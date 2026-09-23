"""Async HTTP fetching and HTML-to-text extraction."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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


class BlockedURL(httpx.RequestError):
    """A URL (or redirect target) the pipeline refuses to fetch."""


def is_public_http_url(url: httpx.URL) -> bool:
    """http(s) only, and never an IP literal in a private, loopback,
    link-local (cloud metadata) or otherwise reserved range. URLs come from
    third-party articles, so the runner must not be pointed at itself."""
    if url.scheme not in ("http", "https") or not url.host:
        return False
    host = url.host.strip("[]").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".internal"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return ip.is_global


async def _check_request(request: httpx.Request) -> None:
    # Runs for the first request and for every redirect hop.
    if not is_public_http_url(request.url):
        raise BlockedURL(f"blocked URL {request.url}", request=request)


class Fetcher:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._sem = asyncio.Semaphore(config.HTTP_MAX_CONCURRENCY)
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=config.HTTP_TIMEOUT,
            follow_redirects=True,
            max_redirects=5,
            headers={"User-Agent": BROWSER_UA},
            event_hooks={"request": [_check_request]},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get(self, url: str, **kwargs) -> httpx.Response | None:
        """GET with a body size cap. None on any failure or oversized body."""
        async with self._sem:
            try:
                async with self._client.stream("GET", url, **kwargs) as resp:
                    if resp.status_code >= 400:
                        log.debug("GET %s -> %s", url, resp.status_code)
                        return None
                    declared = resp.headers.get("content-length", "")
                    if declared.isdigit() and int(declared) > config.MAX_RESPONSE_BYTES:
                        log.debug("GET %s too large (%s bytes)", url, declared)
                        return None
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        body += chunk
                        if len(body) > config.MAX_RESPONSE_BYTES:
                            log.debug("GET %s exceeded %d bytes", url, config.MAX_RESPONSE_BYTES)
                            return None
                    # Body is already decoded, so drop the encoding headers.
                    headers = {k: v for k, v in resp.headers.items()
                               if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")}
                    return httpx.Response(resp.status_code, headers=headers,
                                          content=bytes(body), request=resp.request)
            except (httpx.HTTPError, asyncio.TimeoutError, ValueError) as exc:
                log.debug("GET %s failed: %s", url, exc)
                return None

    async def get_text(self, url: str, **kwargs) -> str:
        return (await self.get_text_html(url, **kwargs))[0]

    async def get_text_html(self, url: str, **kwargs) -> tuple[str, str]:
        """(text, raw_html). The html is kept so links can be harvested."""
        resp = await self.get(url, **kwargs)
        if resp is None:
            return "", ""
        content_type = resp.headers.get("content-type", "")
        if "html" in content_type or "xml" in content_type or not content_type:
            return html_to_text(resp.text), resp.text
        return resp.text[: config.ARTICLE_TEXT_LIMIT], ""


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


_TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "guccounter")


def normalize_url(url: str) -> str:
    """Stable key for 'have we processed this article': lowercase scheme/host,
    no www, fragment or tracking params, no trailing slash."""
    parts = urlparse(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not k.lower().startswith(_TRACKING_PARAMS)])
    return urlunparse((parts.scheme.lower() or "https", host, parts.path.rstrip("/") or "/", "", query, ""))


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def domain_stem(domain: str | None) -> str | None:
    """'acme.io' -> 'acme'"""
    if not domain:
        return None
    return domain.split(".")[0]
