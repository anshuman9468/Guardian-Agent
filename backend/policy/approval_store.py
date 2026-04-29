"""
approval_store.py — In-memory store for pending tool approval requests.

Lifecycle:
  1. Agent hits NEEDS_APPROVAL → creates a PendingRequest here.
  2. Frontend polls GET /approvals/pending → shows it to admin.
  3. Admin clicks Approve → POST /approve/:id → tool executes, entry removed.
  4. Admin clicks Deny   → POST /deny/:id   → entry removed, no execution.

Each entry is keyed by a UUID request_id.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


# ── Store ─────────────────────────────────────────────────────────────────────

_pending: dict[str, dict[str, Any]] = {}


# ── Write ─────────────────────────────────────────────────────────────────────

def create_request(tool_name: str, args: dict[str, Any]) -> str:
    """
    Store a new pending approval request.

    Returns:
        The generated request_id (UUID string).
    """
    request_id = str(uuid.uuid4())
    _pending[request_id] = {
        "request_id": request_id,
        "tool":       tool_name,
        "args":       args,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return request_id


def pop_request(request_id: str) -> dict[str, Any] | None:
    """Remove and return a pending request (used on approve or deny)."""
    return _pending.pop(request_id, None)


# ── Read ──────────────────────────────────────────────────────────────────────

def get_all() -> list[dict[str, Any]]:
    """Return all pending requests, newest first."""
    return sorted(_pending.values(), key=lambda r: r["created_at"], reverse=True)


def count() -> int:
    return len(_pending)
