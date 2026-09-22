"""Anthropic JSON-output client (extraction + judge fallback)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import config

log = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_json(text: str) -> dict[str, Any]:
    match = _JSON_BLOCK_RE.search(text)
    if match:
        return json.loads(match.group(1))
    return json.loads(text)


async def complete_json(system: str, user: str, max_tokens: int = 1500) -> dict[str, Any]:
    """One call that must return a JSON object."""
    import anthropic

    client = anthropic.AsyncAnthropic()
    resp = await client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system + "\nRespond with a single JSON object and nothing else.",
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    return _parse_json(text)
