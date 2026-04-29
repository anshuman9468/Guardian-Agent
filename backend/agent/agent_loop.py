"""
agent_loop.py — Core agentic reasoning loop.

The loop:
  1. Sends messages to the LLM.
  2. If the LLM requests a tool call → executes it → appends result → loops.
  3. If the LLM returns plain text → that is the final answer.

Design notes:
  - max_iterations prevents runaway loops.
  - Each tool call is appended correctly so the OpenAI message history stays valid.
  - Tool arguments arrive as a JSON string from the API; we parse them before
    handing them to the executor.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from agent.llm_client import call_llm

logger = logging.getLogger(__name__)

# Safety ceiling — stops infinite loops if the model keeps calling tools.
MAX_ITERATIONS = 20

SYSTEM_PROMPT = (
    "You are Guardian Agent, a helpful and precise AI assistant that can use "
    "tools to answer questions accurately. Always prefer using a tool when "
    "real-time or factual data is needed. Reason step-by-step before acting."
)


def run_agent(
    user_input: str,
    tools: list[dict[str, Any]],
    tool_executor: Callable[[str, dict[str, Any]], Any],
    model: str = "google/gemini-2.5-flash",
) -> str:
    """
    Run the agentic loop for a single user turn.

    Args:
        user_input:     The user's message / query.
        tools:          List of OpenAI-format tool definitions.
        tool_executor:  Callable(tool_name, parsed_args) → result string.
        model:          OpenAI model to use.

    Returns:
        The final text response from the agent.

    Raises:
        RuntimeError: If the max iteration limit is exceeded without a final answer.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    logger.info("Agent loop started | user_input=%r", user_input[:120])

    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.debug("Iteration %d/%d", iteration, MAX_ITERATIONS)

        response = call_llm(messages, tools=tools, model=model)
        choice = response.choices[0]
        msg = choice.message

        # ── Tool-call branch ────────────────────────────────────────────────
        if msg.tool_calls:
            # Append the assistant turn that contains the tool call request.
            messages.append(msg)

            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                raw_args = tool_call.function.arguments  # JSON string

                try:
                    parsed_args: dict[str, Any] = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    logger.warning(
                        "Could not parse tool args for %s: %r", tool_name, raw_args
                    )
                    parsed_args = {}

                logger.info("Tool call → %s(%s)", tool_name, parsed_args)

                try:
                    result = tool_executor(tool_name, parsed_args)
                except Exception as exc:  # noqa: BLE001
                    result = f"Error executing tool '{tool_name}': {exc}"
                    logger.exception("Tool execution error for %s", tool_name)

                logger.info("Tool result ← %s: %r", tool_name, str(result)[:200])

                # Append the tool result in the correct OpenAI format.
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(result),
                    }
                )

        # ── Final-answer branch ─────────────────────────────────────────────
        else:
            final_answer = msg.content or ""
            logger.info(
                "Agent loop finished | iterations=%d | answer_len=%d",
                iteration,
                len(final_answer),
            )
            return final_answer

    raise RuntimeError(
        f"Agent exceeded maximum iterations ({MAX_ITERATIONS}) without "
        "producing a final answer. Possible tool-call loop detected."
    )
