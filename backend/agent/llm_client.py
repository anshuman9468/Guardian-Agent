import logging
import os
from typing import Any
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

# ─── Configuration ────────────────────────────────────────────────────────────
BASE_URL = "https://openrouter.ai/api/v1"
MODEL    = "google/gemini-2.5-flash"
DEFAULT_MODEL = MODEL

logger = logging.getLogger(__name__)

# ─── OpenRouter Client ────────────────────────────────────────────────────────

def _get_client() -> AsyncOpenAI | None:
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return None
        
    return AsyncOpenAI(
        api_key=key,
        base_url=BASE_URL,
        default_headers={
            "HTTP-Referer": "https://guardian-agent-ten.vercel.app", # Updated to your Vercel URL
            "X-Title": "Guardian Agent"
        }
    )

# ─── Core LLM Call ────────────────────────────────────────────────────────────

async def call_llm(
    messages: list[dict[str, Any]],
    tools:    list[dict[str, Any]] | None = None,
    model:    str | None = None,
    tool_choice: str | dict | None = None,
) -> ChatCompletion:
    """
    OpenRouter-exclusive LLM caller with required headers.
    """
    client = _get_client()
    if not client:
        raise EnvironmentError("OPENROUTER_API_KEY is not set in environment variables.")

    target_model = model or MODEL
    logger.info("Calling OpenRouter | model=%s", target_model)
    
    kwargs: dict[str, Any] = {
        "model":      target_model,
        "messages":   messages,
        "max_tokens": 1500
    }
    
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice or "auto"

    try:
        return await client.chat.completions.create(**kwargs)
    except Exception as e:
        logger.error(f"OpenRouter API call failed: {e}")
        raise e
