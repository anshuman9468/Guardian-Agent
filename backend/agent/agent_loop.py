"""
agent_loop.py — Async agent loop with native OpenAI tool_calls + MCP execution.

Architecture (final):
  User message
       │
  call_llm(messages, tools=live_mcp_tools)
       │
  LLM returns tool_calls?
  YES ─→ for each call:
           1. 🛡️ Policy Engine check
           2. Route to MCP server OR hardcoded fallback
           3. Append result → loop
  NO  ─→ Return final answer

Key improvements over Chunk 2:
  - Fully async (no blocking calls)
  - Native tool_calls (not fragile JSON parsing)
  - Dynamic tools from MCP registry — no hardcoded lists
  - Policy engine gates EVERY tool call
  - Approval store captures NEEDS_APPROVAL requests
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Callable, Awaitable

from agent.llm_client import call_llm, DEFAULT_MODEL
from policy import approval_store
from policy.policy_engine import PolicyResult, evaluate as policy_evaluate

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 15

_SANDBOX = os.getenv(
    "MCP_FILESYSTEM_ROOT",
    os.path.join(os.path.dirname(__file__), "..", "..", "guardian-sandbox"),
)
_SANDBOX = os.path.abspath(_SANDBOX)

SYSTEM_PROMPT = f"""\
You are Guardian Agent, an AI assistant with access to real tools.

CRITICAL RULES — follow these without exception:
1. ALWAYS call a tool when one exists for the task. NEVER answer from memory.
2. For ALL file and directory operations, use the path: {_SANDBOX}
   - List files  → call list_directory with path="{_SANDBOX}"
   - Read a file → call read_file with path="{_SANDBOX}/<filename>"
   - Write a file→ call write_file with path="{_SANDBOX}/<filename>" and content=...
3. For time questions → call get_time
4. For math questions → call add_numbers
5. Do NOT say you "cannot" do something if a tool exists for it.
6. If unsure of the exact path, call list_allowed_directories first.
"""


# ── Type alias ────────────────────────────────────────────────────────────────

AsyncToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]


# ── Main agent loop ───────────────────────────────────────────────────────────

async def run_agent(
    user_input:    str,
    tools:         list[dict[str, Any]],
    tool_executor: AsyncToolExecutor,
    model:         str = DEFAULT_MODEL,
) -> str:
    """
    Async agent loop using native OpenAI tool_calls.

    Args:
        user_input:     The user's message.
        tools:          OpenAI-format tool definitions (from MCP registry).
        tool_executor:  async (tool_name, args) → result string.
        model:          OpenRouter model string.

    Returns:
        Final text answer from the agent.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_input},
    ]

    logger.info("Agent loop started | input=%r | tools=%d", user_input[:80], len(tools))

    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.debug("Iteration %d/%d", iteration, MAX_ITERATIONS)

        response = await call_llm(messages, tools=tools or None, model=model)
        choice   = response.choices[0]
        msg      = choice.message

        # Debug print (temp)
        print(f"[iter {iteration}] finish={choice.finish_reason} | tool_calls={bool(msg.tool_calls)}")

        # ── Tool-call branch ──────────────────────────────────────────────────
        if msg.tool_calls:
            messages.append(msg)  # append assistant message with tool_calls

            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                try:
                    raw_args = tool_call.function.arguments or "{}"
                    args: dict[str, Any] = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}

                logger.info("Tool call → %s(%s)", tool_name, args)

                # 🛡️ Policy check
                policy = policy_evaluate(tool_name, args)

                if policy.status == PolicyResult.BLOCKED:
                    tool_result = f"❌ Tool '{tool_name}' is blocked by policy: {policy.reason}"
                    logger.warning("BLOCKED | tool=%s", tool_name)

                elif policy.status == PolicyResult.NEEDS_APPROVAL:
                    request_id = approval_store.create_request(tool_name, args)
                    logger.info("NEEDS_APPROVAL | tool=%s | request_id=%s", tool_name, request_id)
                    tool_result = (
                        f"⏳__APPROVAL_PENDING__{request_id}__  "
                        f"Tool '{tool_name}' requires human approval. "
                        f"Request ID: {request_id}"
                    )

                elif policy.status == PolicyResult.INVALID_INPUT:
                    tool_result = f"⚠️ Invalid input for '{tool_name}': {policy.reason}"
                    logger.warning("INVALID_INPUT | tool=%s", tool_name)

                else:
                    # ✅ Allowed — execute via MCP or fallback
                    try:
                        tool_result = await tool_executor(tool_name, args)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Tool execution error for %s", tool_name)
                        tool_result = f"Error executing '{tool_name}': {exc}"

                logger.info("Tool result | %s → %r", tool_name, str(tool_result)[:200])

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tool_call.id,
                    "content":      str(tool_result),
                })

        # ── Final answer branch ───────────────────────────────────────────────
        else:
            final = msg.content or ""
            logger.info("Agent done | iterations=%d | answer_len=%d", iteration, len(final))
            return final

    raise RuntimeError(
        f"Agent exceeded {MAX_ITERATIONS} iterations without a final answer."
    )
