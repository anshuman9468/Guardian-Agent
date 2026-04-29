"""
tools.py — Tool registry: definitions + executor.

In Chunk 1 we use dummy/hardcoded tools.
Future chunks will swap this out for real MCP-backed tools.

To add a new tool:
  1. Add its OpenAI schema to TOOL_DEFINITIONS.
  2. Add a matching handler inside _TOOL_HANDLERS.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ─── Tool definitions (OpenAI function-calling schema) ───────────────────────

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": (
                "Returns the current local date and time. "
                "Use this whenever the user asks what time or date it is."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "echo",
            "description": (
                "Echoes back the provided text. Useful for testing the tool pipeline."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to echo back.",
                    }
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_numbers",
            "description": "Adds two numbers together and returns the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First number."},
                    "b": {"type": "number", "description": "Second number."},
                },
                "required": ["a", "b"],
            },
        },
    },
]


# ─── Tool handler implementations ────────────────────────────────────────────

def _handle_get_time(_args: dict[str, Any]) -> str:
    now = datetime.datetime.now()
    return now.strftime("Current date and time: %A, %B %d, %Y at %I:%M:%S %p")


def _handle_echo(args: dict[str, Any]) -> str:
    text = args.get("text", "")
    return f"Echo: {text}"


def _handle_add_numbers(args: dict[str, Any]) -> str:
    try:
        a = float(args["a"])
        b = float(args["b"])
        return f"{a} + {b} = {a + b}"
    except (KeyError, TypeError, ValueError) as exc:
        return f"Error: {exc}"


_TOOL_HANDLERS: dict[str, Any] = {
    "get_time": _handle_get_time,
    "echo": _handle_echo,
    "add_numbers": _handle_add_numbers,
}


# ─── Public executor ─────────────────────────────────────────────────────────

def tool_executor(tool_name: str, args: dict[str, Any]) -> str:
    """
    Dispatch a tool call to the correct handler.

    Args:
        tool_name:  Name of the tool to execute.
        args:       Parsed keyword arguments from the LLM.

    Returns:
        A string result to be sent back to the LLM.
    """
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        logger.warning("Unknown tool requested: %s", tool_name)
        return (
            f"Tool '{tool_name}' is not available. "
            f"Available tools: {', '.join(_TOOL_HANDLERS.keys())}"
        )

    logger.debug("Executing tool: %s | args: %s", tool_name, args)
    return handler(args)
