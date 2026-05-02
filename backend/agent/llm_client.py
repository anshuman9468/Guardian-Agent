import logging
import os
from typing import Any
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

# ─── Configuration ────────────────────────────────────────────────────────────
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GEMINI_BASE_URL     = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Models
OR_MODEL      = "google/gemini-2.5-flash-lite"   # OpenRouter
GEMINI_MODEL  = "gemini-1.5-flash"               # Google direct
DEFAULT_MODEL = OR_MODEL

logger = logging.getLogger(__name__)

# ─── Clients ──────────────────────────────────────────────────────────────────

def _get_or_client() -> AsyncOpenAI | None:
    key = os.getenv("OPENROUTER_API_KEY")
    if not key: return None
    return AsyncOpenAI(api_key=key, base_url=OPENROUTER_BASE_URL)

def _get_gemini_client() -> AsyncOpenAI | None:
    # Check for both GOOGLE_API_KEY (as requested) and GEMINI_API_KEY
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key: return None
    return AsyncOpenAI(api_key=key, base_url=GEMINI_BASE_URL)

# ─── Core LLM Call with Fallback ─────────────────────────────────────────────

async def call_llm(
    messages: list[dict[str, Any]],
    tools:    list[dict[str, Any]] | None = None,
    model:    str | None = None,
    tool_choice: str | dict | None = None,
) -> ChatCompletion:
    """
    Production-level LLM caller:
    - Primary: OpenRouter
    - Fallback: Google Gemini Direct
    """
    or_client = _get_or_client()
    gemini_client = _get_gemini_client()

    # 1. 🔹 Primary: OpenRouter
    if or_client:
        try:
            target_model = model or OR_MODEL
            logger.info("Attempting Primary (OpenRouter) | model=%s", target_model)
            
            kwargs: dict[str, Any] = {
                "model":      target_model,
                "messages":   messages,
                "max_tokens": 1500
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice or "auto"

            return await or_client.chat.completions.create(**kwargs)

        except Exception as e:
            logger.warning(f"OpenRouter failed → switching to Gemini fallback: {e}")

    # 2. 🔹 Fallback: Google Gemini Direct
    if gemini_client:
        try:
            logger.info("Attempting Fallback (Google Gemini) | model=%s", GEMINI_MODEL)
            
            kwargs: dict[str, Any] = {
                "model":      GEMINI_MODEL,
                "messages":   messages,
                "max_tokens": 2000
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice or "auto"

            return await gemini_client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error(f"Fallback also failed: {e}")
            raise e

    # No keys found
    raise EnvironmentError("No valid LLM API keys found (OPENROUTER_API_KEY or GOOGLE_API_KEY).")
