"""Domain resolution and verification.

Domains used to come straight from the extraction model, which guessed them
from the company name — that is how rainmaker.com / zero.com / aqua.com (all
other people's companies) ended up on rows. Nothing here ever builds a domain
out of a name. A domain is only accepted if it was found in the article and
then confirmed by fetching the site.

Order of preference:
  1. a link to the company's own site in the article body
  2. the model's domain, but only if that string actually appears in the article
  3. None
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .fetch import Fetcher, normalize_domain, normalize_name

log = logging.getLogger(__name__)

VERIFY_TIMEOUT = 5.0
VERIFY_TEXT_WINDOW = 2000

# Publishers, wires, social, data providers, infra. A link to any of these is
# never the company's own site.
BLOCKED_SUFFIXES = {
    # publishers + wires
    "techcrunch.com", "reuters.com", "bloomberg.com", "forbes.com", "wsj.com",
    "nytimes.com", "ft.com", "cnbc.com", "theinformation.com", "axios.com",
    "businessinsider.com", "venturebeat.com", "theverge.com", "wired.com",
    "fortune.com", "businesswire.com", "prnewswire.com", "globenewswire.com",
    "prweb.com", "einpresswire.com", "accesswire.com", "newswire.com",
    "finsmes.com", "eu-startups.com", "sifted.eu", "tech.eu", "axios.link",
    # aggregators / platforms
    "google.com", "news.google.com", "yahoo.com", "msn.com", "flipboard.com",
    "medium.com", "substack.com", "wordpress.com", "blogspot.com",
    # social
    "twitter.com", "x.com", "linkedin.com", "facebook.com", "instagram.com",
    "youtube.com", "youtu.be", "tiktok.com", "threads.net", "reddit.com",
    "discord.com", "discord.gg", "slack.com", "t.me", "mastodon.social",
    "bsky.app", "pinterest.com", "snapchat.com",
    # data providers / registries
    "crunchbase.com", "pitchbook.com", "cbinsights.com", "sec.gov",
    "wikipedia.org", "angel.co", "wellfound.com", "producthunt.com",
    "glassdoor.com", "indeed.com", "bloomberglaw.com", "opencorporates.com",
    # dev / infra / misc that show up as incidental links
    "github.com", "gitlab.com", "apple.com", "microsoft.com", "amazon.com",
    "apps.apple.com", "play.google.com", "gravatar.com", "gstatic.com",
    "doubleclick.net", "cloudflare.com", "archive.org", "creativecommons.org",
    "eventbrite.com", "zoom.us", "calendly.com", "notion.so", "airtable.com",
    "typeform.com", "mailchimp.com", "hubspot.com", "salesforce.com",
}

# Corporate suffixes dropped when matching a name against a homepage.
_NAME_SUFFIXES = (
    "incorporated", "corporation", "technologies", "technology", "holdings",
    "software", "systems", "solutions", "ventures", "company", "group",
    "labs", "lab", "inc", "llc", "ltd", "plc", "corp", "co", "gmbh", "bv",
    "sa", "ag", "ai", "io", "hq", "app",
)

_TLD_RE = re.compile(
    r"\b([a-z0-9][a-z0-9-]{1,62}(?:\.[a-z0-9-]{2,63})*\."
    r"(?:com|io|ai|co|net|org|dev|app|xyz|tech|so|sh|health|finance|us|uk|eu|de|fr|ca|com\.au|co\.uk))\b"
)


def _blocked(host: str) -> bool:
    return any(host == b or host.endswith("." + b) for b in BLOCKED_SUFFIXES)


def strip_suffixes(name_key: str) -> str:
    """'rainmakertechnologycorporation' -> 'rainmaker' (normalized input)."""
    changed = True
    while changed:
        changed = False
        for suf in _NAME_SUFFIXES:
            if name_key.endswith(suf) and len(name_key) - len(suf) >= 3:
                name_key = name_key[: -len(suf)]
                changed = True
    return name_key


def candidate_links(html: str, source_url: str, investors: list[str]) -> list[str]:
    """External hosts linked from the article body, best candidates first.

    Publisher, wire, social, data-provider and investor links are dropped.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    publisher = normalize_domain(source_url) or ""
    investor_keys = {normalize_name(i) for i in investors if i}

    counts: dict[str, int] = {}
    for anchor in soup.find_all("a", href=True):
        host = normalize_domain(anchor["href"])
        if not host or "." not in host:
            continue
        if host == publisher or host.endswith("." + publisher) or publisher.endswith("." + host):
            continue
        if _blocked(host):
            continue
        stem = host.split(".")[0]
        if stem in investor_keys or normalize_name(stem) in investor_keys:
            continue
        counts[host] = counts.get(host, 0) + 1
    return sorted(counts, key=lambda h: (-counts[h], len(h)))


def pick_domain(
    name: str,
    html: str,
    text: str,
    source_url: str,
    model_domain: str | None,
    investors: list[str],
) -> tuple[str | None, str]:
    """Choose a candidate domain. Returns (domain, provenance)."""
    name_key = normalize_name(name)
    short = strip_suffixes(name_key)

    links = candidate_links(html, source_url, investors)

    # 1. A linked site whose host looks like the company.
    for host in links:
        stem = normalize_name(host.split(".")[0])
        if stem and (stem == name_key or stem == short or stem.startswith(short) or short.startswith(stem)):
            return host, "article_link_name_match"

    # 2. The model's domain, but only if the article actually says it.
    model = normalize_domain(model_domain)
    if model:
        haystack = f"{text}\n{html}".lower()
        if model in haystack or model.split(".")[0] in {normalize_name(h.split(".")[0]) for h in links}:
            return model, "model_domain_in_article"

    # 3. A single unambiguous external link in the body.
    if len(links) == 1:
        return links[0], "article_link_sole"

    return None, "none"


def _name_in(name: str, title: str, og_site: str, body: str) -> bool:
    """Case-insensitive, punctuation-stripped name match."""
    name_key = normalize_name(name)
    if not name_key:
        return False
    short = strip_suffixes(name_key)
    needles = {n for n in (name_key, short) if len(n) >= 3}

    strong = normalize_name(title) + "|" + normalize_name(og_site)
    weak = strong + "|" + normalize_name(body)

    for n in needles:
        # Short names ('zero', 'aqua') match almost any prose, so they only
        # count in the title / og:site_name, never in loose body text.
        hay = strong if len(n) < 5 else weak
        if n in hay:
            return True
    return False


async def verify(fetcher: Fetcher, domain: str, name: str) -> bool:
    """Fetch the homepage and confirm the company name appears on it."""
    resp = await fetcher.get(f"https://{domain}", timeout=VERIFY_TIMEOUT)
    if resp is None:
        return False
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return False

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    og = soup.find("meta", property="og:site_name")
    og_site = (og.get("content") or "") if og else ""
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    body = soup.get_text(" ", strip=True)[:VERIFY_TEXT_WINDOW]

    return _name_in(name, title, og_site, body)
