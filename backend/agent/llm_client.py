"""
llm_client.py — Thin wrapper around the OpenRouter API (OpenAI-compatible).

Routes requests through OpenRouter to Gemini 2.5 Flash (default).
OpenRouter is a unified gateway — swap the model string to use any
other model (Claude, GPT-4o, Llama, etc.) without changing anything else.

Responsibilities:
  - Initialise the OpenAI-compatible client once (singleton pattern).
  - Expose a single call_llm() function consumed by the agent loop.
  - Surface clear errors when the API key is missing.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletion

# OpenRouter's OpenAI-compatible endpoint.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Default model — Gemini 2.5 Flash via OpenRouter.
DEFAULT_MODEL = "google/gemini-2.5-flash"

logger = logging.getLogger(__name__)


def _build_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY is not set. "
            "Add it to your .env file: OPENROUTER_API_KEY=sk-or-xxxx\n"
            "Get your key at: https://openrouter.ai/keys"
        )
    return OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
    )


# Module-level singleton — created lazily on first call.
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def call_llm(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str = DEFAULT_MODEL,
) -> ChatCompletion:
    """
    Call a model via the OpenRouter API (OpenAI-compatible).

    Args:
        messages:  Conversation history in OpenAI message format.
        tools:     OpenAI-format tool/function definitions (optional).
        model:     OpenRouter model string (default: Gemini 2.5 Flash).
                   Examples:
                     - "google/gemini-2.5-flash"  (default)
                     - "google/gemini-2.5-pro-preview"
                     - "openai/gpt-4o"
                     - "anthropic/claude-3.5-sonnet"

    Returns:
        The raw ChatCompletion object from the OpenAI SDK.
    """
    client = _get_client()

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": 1024,   # Cap tokens to stay within free-tier credits.
    }

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    logger.debug(
        "→ LLM request | model=%s | messages=%d | tools=%d",
        model,
        len(messages),
        len(tools) if tools else 0,
    )

    response = client.chat.completions.create(**kwargs)

    logger.debug(
        "← LLM response | finish_reason=%s | tool_calls=%s",
        response.choices[0].finish_reason,
        bool(response.choices[0].message.tool_calls),
    )

    return response
