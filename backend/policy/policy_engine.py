"""
policy_engine.py — Evaluates tool calls against the rule store.

Pipeline:
  evaluate(tool_name, args) →
    1. Check blocked list       → BLOCKED
    2. Check approval list      → NEEDS_APPROVAL
    3. Validate input args      → INVALID_INPUT
    4. All clear                → ALLOWED

Returns a PolicyResult TypedDict so the caller gets structured data
instead of raw strings — easy to extend in Chunk 4+.
"""

from __future__ import annotations

import logging
from typing import Any

from policy import rule_store

logger = logging.getLogger(__name__)


# ── Result type ───────────────────────────────────────────────────────────────

class PolicyResult:
    """
    Structured policy evaluation result.

    Attributes:
        status:  One of ALLOWED | BLOCKED | NEEDS_APPROVAL | INVALID_INPUT
        reason:  Human-readable explanation (empty string when ALLOWED).
    """

    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    INVALID_INPUT = "INVALID_INPUT"

    def __init__(self, status: str, reason: str = "") -> None:
        self.status = status
        self.reason = reason

    @property
    def is_allowed(self) -> bool:
        return self.status == self.ALLOWED

    def __repr__(self) -> str:
        return f"PolicyResult(status={self.status!r}, reason={self.reason!r})"


# ── Input validator ───────────────────────────────────────────────────────────

def _validate_inputs(tool_name: str, args: dict[str, Any]) -> PolicyResult:
    """
    Validate tool arguments against per-tool input rules.

    Returns INVALID_INPUT with a reason if any rule is violated,
    ALLOWED otherwise.
    """
    rules = rule_store.get_input_rules(tool_name)

    for rule in rules:
        field = rule["field"]
        value = args.get(field)

        # Type check
        expected_type = rule.get("type")
        if expected_type == "number" and value is not None:
            if not isinstance(value, (int, float)):
                return PolicyResult(
                    PolicyResult.INVALID_INPUT,
                    f"Field '{field}' must be a number, got {type(value).__name__}.",
                )
            # Range checks
            if "min" in rule and value < rule["min"]:
                return PolicyResult(
                    PolicyResult.INVALID_INPUT,
                    f"Field '{field}' value {value} is below minimum {rule['min']}.",
                )
            if "max" in rule and value > rule["max"]:
                return PolicyResult(
                    PolicyResult.INVALID_INPUT,
                    f"Field '{field}' value {value} exceeds maximum {rule['max']}.",
                )

        if expected_type == "string" and value is not None:
            if not isinstance(value, str):
                return PolicyResult(
                    PolicyResult.INVALID_INPUT,
                    f"Field '{field}' must be a string.",
                )
            max_len = rule.get("max_length")
            if max_len and len(value) > max_len:
                return PolicyResult(
                    PolicyResult.INVALID_INPUT,
                    f"Field '{field}' exceeds max length of {max_len} characters.",
                )

    return PolicyResult(PolicyResult.ALLOWED)


# ── Main evaluation entry point ───────────────────────────────────────────────

def evaluate(tool_name: str, args: dict[str, Any]) -> PolicyResult:
    """
    Evaluate a tool call against all active policy rules.

    Evaluation order:
      1. Blocked?         → reject immediately.
      2. Needs approval?  → hold for human sign-off.
      3. Input valid?     → reject on bad args.
      4. Allowed.

    Args:
        tool_name:  Name of the tool being requested.
        args:       Parsed arguments for the tool call.

    Returns:
        PolicyResult with status and optional reason.
    """
    logger.info("Policy check | tool=%s | args=%s", tool_name, args)

    # ── 1. Blocked ────────────────────────────────────────────────────────────
    if rule_store.is_blocked(tool_name):
        result = PolicyResult(
            PolicyResult.BLOCKED,
            f"Tool '{tool_name}' is blocked by policy.",
        )
        logger.warning("BLOCKED | tool=%s", tool_name)
        return result

    # ── 2. Needs approval ─────────────────────────────────────────────────────
    if rule_store.needs_approval(tool_name):
        result = PolicyResult(
            PolicyResult.NEEDS_APPROVAL,
            f"Tool '{tool_name}' requires human approval before execution.",
        )
        logger.info("NEEDS_APPROVAL | tool=%s", tool_name)
        return result

    # ── 3. Input validation ───────────────────────────────────────────────────
    validation = _validate_inputs(tool_name, args)
    if not validation.is_allowed:
        logger.warning("INVALID_INPUT | tool=%s | reason=%s", tool_name, validation.reason)
        return validation

    # ── 4. All clear ──────────────────────────────────────────────────────────
    logger.info("ALLOWED | tool=%s", tool_name)
    return PolicyResult(PolicyResult.ALLOWED)
