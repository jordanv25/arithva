"""Shared helpers for every Arithva tool.

Two rules are enforced here rather than left to each tool author:

1. Every tool result carries a source and a timestamp. A number with no
   provenance never reaches the user.
2. A tool that cannot answer says so. It never guesses, and the agent is
   required to read the refusal out loud rather than filling the gap itself.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_cache: dict[str, Any] = {}


def load_data(filename: str) -> dict:
    """Load a JSON data file, cached after first read."""
    if filename not in _cache:
        with open(DATA_DIR / filename, encoding="utf-8") as handle:
            _cache[filename] = json.load(handle)
    return _cache[filename]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ok(value: Any, source: str, *, source_url: str | None = None,
       confidence: str | None = None, **extra: Any) -> dict:
    """A successful tool result."""
    result = {
        "status": "ok",
        "value": value,
        "source": source,
        "as_of": now_iso(),
    }
    if source_url:
        result["source_url"] = source_url
    if confidence:
        result["confidence"] = confidence
    result.update(extra)
    return result


def unavailable(reason: str, *, source: str | None = None) -> dict:
    """A tool that could not answer.

    The agent must speak this reason. It must not substitute its own knowledge:
    'I don't know' is a correct answer, an invented figure is not.
    """
    return {
        "status": "unavailable",
        "reason": reason,
        "source": source,
        "as_of": now_iso(),
        "agent_instruction": "Tell the user this is unavailable and why. Do not supply a number from your own knowledge.",
    }


def refused(reason: str, **extra: Any) -> dict:
    """A tool call the system declines on policy grounds, not a failure."""
    result = {
        "status": "refused",
        "reason": reason,
        "as_of": now_iso(),
        "agent_instruction": "Tell the user plainly that this action is not permitted and why.",
    }
    result.update(extra)
    return result
