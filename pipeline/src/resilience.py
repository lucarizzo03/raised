"""Retries, model-call concurrency limits and per-item failure isolation.

A single flaky model call used to abort the whole daily run and throw away
every call already paid for. Now each company fails on its own and is left
out of the run (it is rediscovered next run while still inside the ingest
window). If too many items in one stage fail, the provider is treated as down
and the run aborts before anything is persisted, so an outage never seeds
empty data or consumes the one-time backfill.
"""

from __future__ import annotations

import asyncio
import logging
import random
import weakref
from collections.abc import Awaitable, Callable, Iterable
from typing import TypeVar

from . import config

log = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")

_TRANSIENT_STATUS = {408, 409, 429}


class StageFailure(RuntimeError):
    """Too many items failed in one stage; the run must not be persisted."""


class OutOfFunds(StageFailure):
    """A model provider refused for billing reasons. The run stops at once and
    writes nothing; the next run after funds are added picks up where it left off."""


# Billing refusals come back as ordinary 4xx errors, so they are recognized by
# status plus wording. Anthropic: 400 "Your credit balance is too low ...".
_FUNDS_PHRASES = (
    "credit balance", "insufficient funds", "insufficient credit", "insufficient balance",
    "out of credits", "payment required", "billing", "top up", "purchase credits",
)


def is_out_of_funds(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 402:
        return True
    if status not in (400, 403):
        return False
    text = f"{exc} {getattr(exc, 'body', '') or ''} {getattr(exc, 'message', '') or ''}".lower()
    return any(phrase in text for phrase in _FUNDS_PHRASES)


def _per_loop(factory: Callable[[], T]) -> Callable[[], T]:
    """One instance per running event loop. Semaphores and HTTP clients are
    bound to the loop they are first used on, and tests create a new loop per
    case."""
    cache: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

    def get() -> T:
        loop = asyncio.get_running_loop()
        if loop not in cache:
            cache[loop] = factory()
        return cache[loop]

    return get


model_slots = _per_loop(lambda: asyncio.Semaphore(config.MODEL_MAX_CONCURRENCY))


def is_transient(exc: BaseException) -> bool:
    """Rate limits, overloads, 5xx, timeouts and dropped connections."""
    if isinstance(exc, (TimeoutError, ConnectionError, asyncio.TimeoutError)):
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int):
        return status in _TRANSIENT_STATUS or status >= 500
    try:
        import httpx

        if isinstance(exc, httpx.TransportError):
            return True
    except ImportError:  # pragma: no cover
        pass
    try:
        import anthropic

        if isinstance(exc, anthropic.APIConnectionError):
            return True
    except ImportError:  # pragma: no cover
        pass
    return False


def provider_name(exc: BaseException) -> str:
    module = type(exc).__module__
    if module.startswith("anthropic"):
        return "Anthropic (Claude)"
    if "typesafe" in module:
        return "TypeSafe (Jev)"
    return "Model provider"


def _delay(attempt: int, exc: BaseException) -> float:
    retry_after_ms = getattr(exc, "retry_after_ms", None)
    if isinstance(retry_after_ms, (int, float)) and retry_after_ms > 0:
        return min(retry_after_ms / 1000, config.RETRY_MAX_DELAY)
    base = config.RETRY_BASE_DELAY * (2 ** attempt)
    return min(base, config.RETRY_MAX_DELAY) * random.uniform(0.5, 1.0)


async def with_retries(call: Callable[[], Awaitable[R]], *, what: str) -> R:
    """Run `call`, retrying transient failures with exponential backoff."""
    attempts = config.MODEL_MAX_RETRIES + 1
    for attempt in range(attempts):
        try:
            return await call()
        except Exception as exc:
            if attempt == attempts - 1 or not is_transient(exc):
                raise
            delay = _delay(attempt, exc)
            log.warning("%s failed (%s); retry %d/%d in %.1fs",
                        what, type(exc).__name__, attempt + 1, attempts - 1, delay)
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")


async def run_each(
    items: Iterable[T],
    fn: Callable[[T], Awaitable[R]],
    *,
    stage: str,
    label: Callable[[T], str] = str,
) -> tuple[list[R | None], list[T]]:
    """Run `fn` over every item concurrently, isolating failures.

    Returns (results aligned with items, None where it failed; failed items).
    Raises StageFailure when the failure rate exceeds MAX_STAGE_FAILURE_RATE.
    """
    items = list(items)
    if not items:
        return [], []
    outcomes = await asyncio.gather(*(fn(i) for i in items), return_exceptions=True)
    # Out of funds is not a per-item problem: stop the whole run, whatever the
    # failure rate, so a day is never saved half-finished.
    for outcome in outcomes:
        if isinstance(outcome, Exception) and is_out_of_funds(outcome):
            raise OutOfFunds(f"{stage}: {provider_name(outcome)} account is out of funds") from outcome
    results: list[R | None] = []
    failed: list[T] = []
    first_error: BaseException | None = None
    for item, outcome in zip(items, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            if not isinstance(outcome, Exception):
                raise outcome  # cancellation / interrupt
            log.warning("%s failed for %s: %s: %s", stage, label(item), type(outcome).__name__, outcome)
            failed.append(item)
            results.append(None)
            first_error = first_error or outcome
        else:
            results.append(outcome)
    if failed:
        rate = len(failed) / len(items)
        log.warning("%s: %d of %d failed (%.0f%%)", stage, len(failed), len(items), rate * 100)
        if rate > config.MAX_STAGE_FAILURE_RATE:
            raise StageFailure(
                f"{stage}: {len(failed)} of {len(items)} failed, over the "
                f"{config.MAX_STAGE_FAILURE_RATE:.0%} limit; aborting before persisting"
            ) from first_error
    return results, failed
