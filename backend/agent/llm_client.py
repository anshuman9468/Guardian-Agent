import logging
import os
from typing import Any
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
import openai

# Configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GEMINI_BASE_URL     = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Default Models
OR_MODEL     = "google/gemini-2.5-flash-lite"
GEMINI_MODEL = "gemini-1.5-flash"

logger = logging.getLogger(__name__)

# Clients
_or_client: AsyncOpenAI | None = None
_gemini_client: AsyncOpenAI | None = None

def _get_or_client() -> AsyncOpenAI | None:
    global _or_client
    key = os.getenv("OPENROUTER_API_KEY")
    if not key: return None
    if _or_client is None:
        _or_client = AsyncOpenAI(api_key=key, base_url=OPENROUTER_BASE_URL)
    return _or_client

def _get_gemini_client() -> AsyncOpenAI | None:
    global _gemini_client
    key = os.getenv("GEMINI_API_KEY")
    if not key: return None
    if _gemini_client is None:
        _gemini_client = AsyncOpenAI(api_key=key, base_url=GEMINI_BASE_URL)
    return _gemini_client

async def call_llm(
    messages: list[dict[str, Any]],
    tools:    list[dict[str, Any]] | None = None,
    model:    str | None = None,
    tool_choice: str | dict | None = None,
) -> ChatCompletion:
    """
    Async call to LLM with automatic fallback from OpenRouter to Google Gemini.
    """
    or_client = _get_or_client()
    gemini_client = _get_gemini_client()

    # 1. Try OpenRouter First (if key exists)
    if or_client:
        try:
            logger.info("Attempting primary LLM call (OpenRouter)")
            kwargs: dict[str, Any] = {
                "model":      model or OR_MODEL,
                "messages":   messages,
                "max_tokens": 540,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice or "auto"

            return await or_client.chat.completions.create(**kwargs)

        except Exception as e:
            logger.warning(f"OpenRouter failed: {e}. Switching to Gemini fallback...")
    
    # 2. Fallback to Gemini
    if gemini_client:
        logger.info("Attempting fallback LLM call (Google Gemini)")
        try:
            kwargs: dict[str, Any] = {
                "model":      GEMINI_MODEL, # Gemini uses its own model IDs
                "messages":   messages,
                "max_tokens": 1000, # Gemini allows more tokens
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice or "auto"

            return await gemini_client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error(f"Gemini fallback also failed: {e}")
            raise e

    raise EnvironmentError("No valid LLM API keys found (OpenRouter or Gemini).")
