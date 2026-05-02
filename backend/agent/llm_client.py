import logging
import os
import json
from typing import Any
from openai import AsyncOpenAI

# ─── Configuration ────────────────────────────────────────────────────────────
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini")
OPENROUTER_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

logger = logging.getLogger(__name__)

# ─── Client ───────────────────────────────────────────────────────────────────

def _get_client():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENROUTER_API_KEY is not set.")
    return AsyncOpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)

# ─── Mappers ──────────────────────────────────────────────────────────────────

def _map_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalize messages into OpenAI-compatible shape for OpenRouter.
    Keeps system/user/assistant/tool roles intact.
    """
    mapped: list[dict[str, Any]] = []
    for m in messages or []:
        role = m.get("role", "user")
        msg: dict[str, Any] = {"role": role}

        # Pass through tool call messages if present; otherwise content.
        if "content" in m:
            msg["content"] = m.get("content")
        if role == "tool":
            # OpenAI schema: tool messages should include tool_call_id
            if "tool_call_id" in m:
                msg["tool_call_id"] = m["tool_call_id"]
            elif "name" in m:
                # Some adapters send name instead; keep it as best-effort.
                msg["name"] = m["name"]

        # Some callers might attach tool_calls on assistant messages.
        if role == "assistant" and "tool_calls" in m and m["tool_calls"] is not None:
            msg["tool_calls"] = m["tool_calls"]

        mapped.append(msg)
    return mapped

def _map_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """
    Tools are expected in OpenAI format:
    [{"type":"function","function":{"name","description","parameters"}}]
    """
    if not tools:
        return None
    normalized: list[dict[str, Any]] = []
    for t in tools:
        if t.get("type") == "function" and "function" in t:
            normalized.append(t)
        elif "function" in t:
            normalized.append({"type": "function", "function": t["function"]})
    return normalized or None

# ─── OpenAI Compatibility Adapter ───────────────────────────────────────────

class MockMessage:
    def __init__(self, content, tool_calls=None):
        self.content = content or ""
        self.tool_calls = tool_calls
        self.role = "assistant"

    def __getitem__(self, key):
        if key == "content": return self.content
        if key == "tool_calls": return self.tool_calls
        if key == "role": return self.role
        raise KeyError(f"'{key}' not found in MockMessage")

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

class MockChoice:
    def __init__(self, content, tool_calls=None):
        self.message = MockMessage(content, tool_calls)
        self.finish_reason = "tool_calls" if tool_calls else "stop"

class MockResponse:
    def __init__(self, content, tool_calls=None, model="gemini"):
        self.choices = [MockChoice(content, tool_calls)]
        self.model = model

# ─── Core LLM Call ────────────────────────────────────────────────────────────

async def call_llm(messages, tools=None, model=None, tool_choice=None):
    client = _get_client()
    target_model = model or DEFAULT_MODEL

    # 1. Wrap the last message in a safe rules template (avoid over-strict prompts)
    if messages and messages[-1]["role"] == "user":
        orig = messages[-1]["content"]
        messages[-1]["content"] = f"""
You are an AI assistant. Your task is to provide clean, structured, and final answers only.

Rules:
- No unnecessary explanation
- Keep it concise
- Follow the requested format strictly
- If JSON is requested: return valid JSON ONLY
- Otherwise: return structured text

USER INPUT:
{orig}
"""

    try:
        oai_messages = _map_messages(messages)
        oai_tools = _map_tools(tools)

        # 2. Call OpenRouter (OpenAI-compatible)
        response = await client.chat.completions.create(
            model=target_model,
            messages=oai_messages,
            tools=oai_tools,
            tool_choice=tool_choice,
            temperature=0.3,
            max_tokens=1000,
        )
        logger.debug("Raw OpenRouter response: %r", response)

        choice = response.choices[0] if response.choices else None
        msg = choice.message if choice else None

        text = (msg.content or "").strip() if msg and msg.content else ""
        tool_calls = getattr(msg, "tool_calls", None) if msg else None

        if not text and not tool_calls:
            text = "⚠️ Empty response from model (no message content/tool_calls)."

        return MockResponse(text, tool_calls, model=target_model)

    except Exception as e:
        logger.exception("OpenRouter API error")
        raise e
