"""
agent_loop.py — Chunk 2: LLM-driven JSON action routing.

Architecture:
  1. System prompt instructs the LLM to respond in a structured JSON format.
  2. We parse the LLM's JSON output to determine the action.
  3. A router executes the chosen tool (or returns the final answer).
  4. [Placeholder] Policy engine will gate tool execution in Chunk 3.

This replaces the native OpenAI function-calling approach with a
system-controlled JSON routing pattern — giving us full control over
the decision pipeline.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from agent.llm_client import call_llm
from policy.policy_engine import PolicyResult, evaluate as policy_evaluate

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10  # Safety ceiling against infinite loops.

# ── Step 1: System prompt — LLM outputs structured JSON ──────────────────────

SYSTEM_PROMPT = """You are an AI agent with access to tools.

When a tool is needed to answer the user, respond ONLY with valid JSON:

{
  "action": "tool_name",
  "args": {}
}

If NO tool is needed, respond ONLY with valid JSON:

{
  "action": "none",
  "response": "your answer here"
}

Available tools:
- get_time     → no args needed
- echo         → args: { "text": "<string>" }
- add_numbers  → args: { "a": <number>, "b": <number> }

CRITICAL RULES:
- NEVER respond with plain text — always output valid JSON.
- Do NOT wrap JSON in markdown code blocks.
- If a relevant tool exists, ALWAYS use it instead of answering directly.
"""


# ── Step 2: JSON parser — handles LLM quirks ─────────────────────────────────

def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    """
    Extract and parse a JSON object from the LLM's response.

    Handles two common LLM quirks:
      - Wrapping JSON in ```json ... ``` code fences.
      - Extra whitespace or trailing text.

    Returns parsed dict, or None if parsing fails.
    """
    if not raw:
        return None

    # Strip markdown code fences if the LLM wrapped the JSON.
    stripped = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        # Try to extract the first {...} block as a fallback.
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

    logger.warning("Could not parse LLM JSON response: %r", raw[:300])
    return None


# ── Step 3: Router — decides tool call or final answer ────────────────────────

def _route(
    decision: dict[str, Any],
    tool_executor: Callable[[str, dict[str, Any]], Any],
) -> str | None:
    """
    Route the parsed LLM decision.

    Returns:
      - A string result if the action was handled.
      - None if the action is "none" (signal to return the response field).
    """
    action = decision.get("action", "none")

    if action == "none":
        return None  # Caller will extract decision["response"].

    tool_name = action
    args = decision.get("args", {})

    # ── 🛡️ POLICY ENGINE (Chunk 3) ───────────────────────────────────────────
    policy = policy_evaluate(tool_name, args)

    if policy.status == PolicyResult.BLOCKED:
        logger.warning("Policy BLOCKED | tool=%s | reason=%s", tool_name, policy.reason)
        return f"❌ Tool blocked by policy: {policy.reason}"

    if policy.status == PolicyResult.NEEDS_APPROVAL:
        logger.info("Policy NEEDS_APPROVAL | tool=%s", tool_name)
        return (
            f"⏳ Tool '{tool_name}' requires human approval before it can run. "
            "(Approval workflow coming in Chunk 4)"
        )

    if policy.status == PolicyResult.INVALID_INPUT:
        logger.warning("Policy INVALID_INPUT | tool=%s | reason=%s", tool_name, policy.reason)
        return f"⚠️ Invalid input for tool '{tool_name}': {policy.reason}"

    # ── ✅ ALLOWED — execute the tool ─────────────────────────────────────────

    try:
        result = tool_executor(tool_name, args)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Tool execution error for %s", tool_name)
        result = f"Error executing tool '{tool_name}': {exc}"

    logger.info("Router ← result: %r", str(result)[:200])
    return f"(via tool: {tool_name}) {result}"


# ── Main agent loop ───────────────────────────────────────────────────────────

def run_agent(
    user_input: str,
    tools: list[dict[str, Any]],                    # kept for API compatibility
    tool_executor: Callable[[str, dict[str, Any]], Any],
    model: str = "google/gemini-2.5-flash",
) -> str:
    """
    Run the Chunk 2 agentic loop (LLM-driven JSON routing).

    Args:
        user_input:     The user's message / query.
        tools:          Tool definitions (passed for compatibility; not sent
                        to LLM in this architecture — routing is JSON-based).
        tool_executor:  Callable(tool_name, parsed_args) → result string.
        model:          OpenRouter model string.

    Returns:
        The final text response from the agent.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    logger.info("Agent loop started | user_input=%r", user_input[:120])

    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.debug("Iteration %d/%d", iteration, MAX_ITERATIONS)

        # NOTE: We do NOT pass `tools` here — routing is done via JSON parsing,
        # not via OpenAI native function-calling.
        response = call_llm(messages, tools=None, model=model)
        msg = response.choices[0].message
        raw_content = msg.content or ""

        # CHANGE 5 — Debug print (temp, remove in production)
        print("LLM RESPONSE:", msg)

        # ── Step 2: Parse the LLM's JSON decision ────────────────────────────
        decision = _parse_llm_json(raw_content)

        if decision is None:
            # Parsing failed entirely — treat raw text as the final answer.
            logger.warning("JSON parse failed; returning raw response as fallback.")
            return raw_content

        # ── Step 3: Route the decision ────────────────────────────────────────
        tool_result = _route(decision, tool_executor)

        if tool_result is None:
            # action == "none" → LLM is answering directly.
            final_answer = decision.get("response", raw_content)
            logger.info(
                "Agent loop finished (no tool) | iterations=%d | answer_len=%d",
                iteration,
                len(final_answer),
            )
            return final_answer

        # Tool was executed — feed result back for a follow-up LLM turn.
        messages.append({"role": "assistant", "content": raw_content})
        messages.append({"role": "user", "content": f"Tool result: {tool_result}"})

        logger.info(
            "Tool executed on iteration %d — looping for final answer.", iteration
        )

    raise RuntimeError(
        f"Agent exceeded maximum iterations ({MAX_ITERATIONS}) "
        "without producing a final answer."
    )
