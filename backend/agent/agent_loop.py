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

def _get_system_prompt() -> str:
    return """\
You are an AI agent. Follow these rules:
1. ALWAYS call a tool for external tasks (files, APIs, web). NEVER answer from memory.
2. Use ABSOLUTE paths for all file operations. Do NOT refuse access; the policy engine handles security.
3. For URLs, prepend 'https://' if missing.
4. If a tool is blocked, report the exact failure to the user.
5. Return tool calls immediately when needed. Be concise.
"""


# ── Type alias ────────────────────────────────────────────────────────────────

AsyncToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]


# ── Main agent loop ───────────────────────────────────────────────────────────

async def run_agent(
    user_input:    str,
    history:       list[dict[str, str]] | None,
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
        {"role": "system", "content": _get_system_prompt()},
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    logger.info("Agent loop started | input=%r | tools=%d", user_input[:80], len(tools))

    for iteration in range(1, MAX_ITERATIONS + 1):
        # 🔥 FORCED TOOL EXECUTION: Determine if the prompt implies a tool
        lower_input = user_input.lower()
        # Dynamically build keywords from all available tools instead of a hardcoded list
        tool_keywords = []
        if tools:
            for t in tools:
                name = t["function"]["name"].lower()
                tool_keywords.append(name)
                tool_keywords.extend(name.split("_"))
        
        requires_tool = any(kw in lower_input for kw in tool_keywords if len(kw) > 2)
        
        tool_choice = "required" if (iteration == 1 and requires_tool) else "auto"
        
        logger.debug("Iteration %d/%d", iteration, MAX_ITERATIONS)

        response = await call_llm(messages, tools=tools or None, model=model, tool_choice=tool_choice)
        choice   = response.choices[0]
        msg      = choice.message
        
        # Defensive access to finish_reason and tool_calls
        finish_reason = getattr(choice, "finish_reason", "stop")
        tool_calls    = getattr(msg, "tool_calls", None)

        # Debug print (temp)
        print(f"[iter {iteration}] finish={finish_reason} | tool_calls={bool(tool_calls)}")

        # ── Tool-call branch ──────────────────────────────────────────────────
        if tool_calls:
            messages.append(msg)  # append assistant message with tool_calls

            for tool_call in tool_calls:
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
                    msg_text = f"❌ Blocked. Tool '{tool_name}' is blocked by policy: {policy.reason}"
                    logger.warning("BLOCKED | tool=%s", tool_name)
                    return msg_text

                elif policy.status == PolicyResult.NEEDS_APPROVAL:
                    # 🛑 PAUSE EXECUTION: Stop immediately and ask user
                    request_id = approval_store.create_request(tool_name, args)
                    logger.info("NEEDS_APPROVAL | tool=%s | request_id=%s", tool_name, request_id)
                    return f"⏳ Tool '{tool_name}' requires human approval before proceeding. Request ID: {request_id}"

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
