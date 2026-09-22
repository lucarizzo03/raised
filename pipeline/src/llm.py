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


async def complete_json(system: str, user: str, max_tokens: int = 1500, *, schema: dict | None = None) -> dict[str, Any]:
    """One call that must return a JSON object."""
    import anthropic

    client = anthropic.AsyncAnthropic()
    options = {}
    if schema is not None:
        options = {
            "tools": [{"name": "return_json", "description": "Return the extracted funding announcement.", "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": "return_json"},
        }
    resp = await client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system + ("\nReturn the result using return_json." if schema is not None else "\nRespond with a single JSON object and nothing else."),
        messages=[{"role": "user", "content": user}],
        **options,
    )
    if schema is not None:
        for block in resp.content:
            if block.type == "tool_use" and block.name == "return_json" and isinstance(block.input, dict):
                return block.input
        raise ValueError("Extraction did not return structured tool input")
    text = "".join(block.text for block in resp.content if block.type == "text")
    return _parse_json(text)
