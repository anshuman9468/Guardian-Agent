"""
rule_store.py — In-memory rule store for the policy engine.

Structure:
  blocked_tools   → tools that are ALWAYS rejected.
  approval_tools  → tools that need human approval before executing.
  input_rules     → per-tool argument validation rules.

In Chunk 4+, this will be backed by a database or config file.
For now it is an in-memory dict that can be mutated at runtime
via the /policy/* API endpoints.

Pre-loaded demo rules:
  - No tools blocked by default (add "echo" to test blocking).
  - No tools requiring approval by default (add "add_numbers" to test).
  - Input rule: add_numbers → both a and b must be <= 1,000,000.
"""

from __future__ import annotations

from typing import Any


# ── Master rule store ─────────────────────────────────────────────────────────

_store: dict[str, Any] = {
    # Tools that are completely forbidden. Agent returns BLOCKED immediately.
    "blocked_tools": [],

    # Tools that need human sign-off. Agent returns NEEDS_APPROVAL.
    # In Chunk 4 this will trigger a real approval workflow.
    "approval_tools": [],

    # Per-tool argument validation rules.
    # Each entry: { "field": str, "type": type|None, "max": num|None, "min": num|None }
    "input_rules": {
        "add_numbers": [
            {"field": "a", "type": "number", "min": -1_000_000, "max": 1_000_000},
            {"field": "b", "type": "number", "min": -1_000_000, "max": 1_000_000},
        ],
        "echo": [
            {"field": "text", "type": "string", "max_length": 500},
        ],
    },
}


# ── Public accessors (keep _store private) ────────────────────────────────────

def get_rules() -> dict[str, Any]:
    """Return a snapshot of the full rule store."""
    return {
        "blocked_tools": list(_store["blocked_tools"]),
        "approval_tools": list(_store["approval_tools"]),
        "input_rules": dict(_store["input_rules"]),
    }


def is_blocked(tool_name: str) -> bool:
    return tool_name in _store["blocked_tools"]


def needs_approval(tool_name: str) -> bool:
    return tool_name in _store["approval_tools"]


def get_input_rules(tool_name: str) -> list[dict[str, Any]]:
    return _store["input_rules"].get(tool_name, [])


# ── Mutators (used by the /policy API) ───────────────────────────────────────

def block_tool(tool_name: str) -> None:
    if tool_name not in _store["blocked_tools"]:
        _store["blocked_tools"].append(tool_name)
    # If it was pending approval, remove it from there too.
    _store["approval_tools"] = [t for t in _store["approval_tools"] if t != tool_name]


def unblock_tool(tool_name: str) -> None:
    _store["blocked_tools"] = [t for t in _store["blocked_tools"] if t != tool_name]


def require_approval(tool_name: str) -> None:
    if tool_name not in _store["approval_tools"]:
        _store["approval_tools"].append(tool_name)
    # Can't need approval AND be blocked simultaneously.
    _store["blocked_tools"] = [t for t in _store["blocked_tools"] if t != tool_name]


def remove_approval(tool_name: str) -> None:
    _store["approval_tools"] = [t for t in _store["approval_tools"] if t != tool_name]
