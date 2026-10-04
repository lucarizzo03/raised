"""Cheap screening before Claude extraction, which is the pipeline's main cost.

Two steps, both on fetched articles that are still inside the window:
  1. Group by the company named in the headline ("Armadin raises $255M ..."),
     so one raise covered by five outlets is extracted once, not five times.
     Companies already stored are skipped outright.
  2. Jev reads each group's headline and opening and skips the ones it is
     confident are not a new pre-seed to Series B raise (late rounds, funds
     raising their own funds, sports, roundups).

Anything uncertain goes on to Claude: a headline that doesn't parse is its
own group, and a Jev "no" below PREFILTER_SKIP_CONFIDENCE is kept.
"""

from __future__ import annotations

import logging
import re

from . import config
from .fetch import normalize_name
from .models import FeedItem
from .resilience import run_each

log = logging.getLogger(__name__)

_VERB = re.compile(
    r"\s+(?:raises|raised|secures|secured|lands|landed|closes|closed|nabs|bags|snags|"
    r"picks up|gets|announces|completes)\b",
    re.IGNORECASE,
)
# Descriptors in front of the name: "London's Metaview", "AI Cyber Startup
# Armadin", "a16z-backed EliseAI", "concrete recycling spinout R2Crete".
_DESCRIPTOR = re.compile(r"^.*(?:'s|’s|-backed|\bstartup|\bspinout|\bspin-off|\bunicorn)\s+", re.IGNORECASE)
_LEAD = re.compile(r"^(?:exclusive|breaking|scoop)\s*[:|\-–—]\s*", re.IGNORECASE)
_SOURCE_PRIORITY = {"techcrunch": 0}
_MIN_SUFFIX = 5  # shorter names ("ai", "flow") are too common to merge on


def headline_company(title: str) -> str | None:
    """Normalized company name from a funding headline, or None if the
    headline doesn't read "<name> raises ..."."""
    title = re.sub(r"\s+[-–—|]\s+[^-–—|]+$", "", title.strip())  # " - Publisher"
    title = _LEAD.sub("", title)
    match = _VERB.search(title)
    if not match:
        return None
    name = _DESCRIPTOR.sub("", title[: match.start()]).strip(" :,")
    if not name or len(name.split()) > 5:
        return None
    return normalize_name(name) or None


def group(items: list[FeedItem], known: set[str] = frozenset()) -> tuple[list[FeedItem], dict[int, list[FeedItem]], list[FeedItem]]:
    """Returns (representatives, {id(rep): its duplicates}, already-known items).

    Only items with text can represent a group, so a paywalled copy is passed
    over for one that fetched. TechCrunch is preferred, then feed order.
    """
    keyed: list[tuple[str, FeedItem]] = []
    singles: list[FeedItem] = []
    for item in items:
        key = headline_company(item.title)
        if key:
            keyed.append((key, item))
        else:
            singles.append(item)
    # Descriptors the pattern misses ("NBFC Company Seeds Fincap") leave a key
    # that ends in a shorter one from the same run ("seedsfincap"): merge them.
    names = sorted({k for k, _ in keyed}, key=len)
    canonical = {k: next((s for s in names if len(s) >= _MIN_SUFFIX and len(s) < len(k) and k.endswith(s)), k)
                 for k in names}
    groups: dict[str, list[FeedItem]] = {}
    for key, item in keyed:
        groups.setdefault(canonical[key], []).append(item)
    reps, dupes, known_items = list(singles), {}, []
    for key, members in groups.items():
        if key in known:
            known_items.extend(members)
            continue
        ranked = sorted(members, key=lambda i: (not i.text, _SOURCE_PRIORITY.get(i.source, 1)))
        reps.append(ranked[0])
        dupes[id(ranked[0])] = ranked[1:]
    log.info("prefilter: %d articles -> %d after grouping (%d duplicates, %d about known companies)",
             len(items), len(reps), sum(len(d) for d in dupes.values()), len(known_items))
    return reps, dupes, known_items


async def screen(items: list[FeedItem]) -> dict[int, float]:
    """Jev's confident "not a new early-stage raise" calls: {id(item): confidence}.
    A failed call keeps the article (it goes on to Claude)."""
    from .judge import backend, _questions

    questions = _questions(early_raise=("noul", {"instructions": (
        "Does this article announce that one startup has just raised a new pre-seed, "
        "seed, Series A or Series B round? Answer no for Series C or later, growth "
        "or late-stage rounds, venture firms raising their own fund, public companies, "
        "acquisitions, IPOs, roundups of several companies, and articles that are not "
        "about a company raising money. If the round has no stage name, answer yes "
        "unless the company is clearly late-stage."
    )}))

    async def ask(item: FeedItem):
        state = f"headline: {item.title}\narticle opening: {item.text[:600]}"
        return (await backend().ask(state, questions))["early_raise"]

    answers, _failed = await run_each(items, ask, stage="prefilter", label=lambda i: i.url)
    skipped = {
        id(item): answer.confidence
        for item, answer in zip(items, answers, strict=True)
        if answer is not None and answer.value == "no" and answer.confidence >= config.PREFILTER_SKIP_CONFIDENCE
    }
    for item in items:
        if id(item) in skipped:
            log.info("prefilter skip (confidence %.2f): %s", skipped[id(item)], item.title)
    log.info("prefilter: Jev skipped %d of %d", len(skipped), len(items))
    return skipped
