"""
llm_client.py — Async wrapper around the OpenRouter API (OpenAI-compatible).

Uses AsyncOpenAI so it plays nicely with FastAPI's event loop.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL       = "google/gemini-2.5-flash-lite"

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENROUTER_API_KEY is not set. "
                "Add it to your .env file: OPENROUTER_API_KEY=sk-or-xxxx\n"
                "Get your key at: https://openrouter.ai/keys"
            )
        _client = AsyncOpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)
    return _client


async def call_llm(
    messages: list[dict[str, Any]],
    tools:    list[dict[str, Any]] | None = None,
    model:    str = DEFAULT_MODEL,
    tool_choice: str | dict | None = None,
) -> ChatCompletion:
    """
    Async call to the OpenRouter API.

    Args:
        messages: Conversation history in OpenAI format.
        tools:    OpenAI tool definitions (optional).
        model:    OpenRouter model string.
        tool_choice: 'auto', 'required', or a specific function dict.

    Returns:
        ChatCompletion response object.
    """
    client = _get_client()

    kwargs: dict[str, Any] = {
        "model":      model,
        "messages":   messages,
        "max_tokens": 540,
    }

    if tools:
        kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        else:
            kwargs["tool_choice"] = "auto"

    logger.debug(
        "→ LLM | model=%s | msgs=%d | tools=%d",
        model, len(messages), len(tools) if tools else 0,
    )

    response = await client.chat.completions.create(**kwargs)

    logger.debug(
        "← LLM | finish=%s | tool_calls=%s",
        response.choices[0].finish_reason,
        bool(response.choices[0].message.tool_calls),
    )
    return response
