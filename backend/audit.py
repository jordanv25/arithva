"""Hash-chained audit log.

Every entry carries the hash of the one before it. Editing an old row breaks
the chain from that row onward, and /api/audit/verify reports exactly where.
That is the point: the log is checkable by anyone, not trusted because we say so.

A single-process SQLite chain is not a distributed ledger, and this code does
not pretend otherwise. It makes silent edits detectable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

GENESIS = "0" * 64


def entry_hash(previous_hash: str, timestamp: str, actor: str, action: str,
               detail: dict) -> str:
    """Hash over the fields that matter, with sorted keys so it is reproducible."""
    payload = json.dumps(
        {
            "previous_hash": previous_hash,
            "timestamp": timestamp,
            "actor": actor,
            "action": action,
            "detail": detail,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def verify_chain(rows: list[dict]) -> dict:
    """Walk the chain and report the first row that does not match.

    Returns the row number rather than a bare true/false, because in the demo
    we deliberately tamper with a row and show the check naming it.
    """
    previous = GENESIS
    for index, row in enumerate(rows):
        detail = row["detail"]
        if isinstance(detail, str):
            detail = json.loads(detail)

        expected = entry_hash(
            previous_hash=row["previous_hash"],
            timestamp=row["timestamp"],
            actor=row["actor"],
            action=row["action"],
            detail=detail,
        )

        if row["previous_hash"] != previous:
            return {
                "intact": False,
                "broken_at_row": index + 1,
                "reason": "This row does not point at the row before it.",
                "entry_id": row.get("id"),
            }
        if row["entry_hash"] != expected:
            return {
                "intact": False,
                "broken_at_row": index + 1,
                "reason": "This row's contents do not match its recorded hash, so it was changed after it was written.",
                "entry_id": row.get("id"),
            }
        previous = row["entry_hash"]

    return {"intact": True, "rows_checked": len(rows)}
