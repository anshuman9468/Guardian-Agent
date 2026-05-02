import logging
import os
import json
from typing import Any
from google import genai
from google.genai import types

# ─── Configuration ────────────────────────────────────────────────────────────
MODEL_NAME = "gemini-2.0-flash-lite-preview-02-05" 
DEFAULT_MODEL = "gemini-2.5-flash-lite" 

logger = logging.getLogger(__name__)

# ─── Client ───────────────────────────────────────────────────────────────────

def _get_client():
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY is not set.")
    return genai.Client(api_key=api_key)

# ─── Mappers ──────────────────────────────────────────────────────────────────

def _map_messages(messages: list[dict[str, Any]]) -> list[types.Content]:
    """Maps OpenAI messages (user, assistant, tool, system) to Gemini roles (user, model)."""
    mapped = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")

        # Gemini only supports 'user' and 'model'
        if role == "user":
            gemini_role = "user"
        else:
            # assistant, tool, system -> model
            gemini_role = "model"
        
        mapped.append(types.Content(
            role=gemini_role, 
            parts=[types.Part(text=str(content))]
        ))
    return mapped

def _map_tools(tools: list[dict[str, Any]]) -> list[types.Tool]:
    if not tools: return None
    declarations = [types.FunctionDeclaration(
        name=t["function"]["name"],
        description=t["function"].get("description", ""),
        parameters=t["function"].get("parameters", {"type": "object", "properties": {}})
    ) for t in tools]
    return [types.Tool(function_declarations=declarations)]

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
    if "/" in target_model: target_model = target_model.split("/")[-1]

    # 1. Wrap the last message in the Strict Rules template
    if messages and messages[-1]["role"] == "user":
        orig = messages[-1]["content"]
        messages[-1]["content"] = f"""
You are an AI assistant. Your task is to provide clean, structured, and final answers only.

STRICT RULES:
1. Do NOT explain your reasoning.
2. Do NOT include thinking steps.
3. Do NOT include unnecessary text.
4. Do NOT repeat the question.
5. Output must be concise and directly usable.

USER INPUT:
{orig}
"""

    config = types.GenerateContentConfig(
        tools=_map_tools(tools),
        temperature=0.3,
        max_output_tokens=1000,
        system_instruction=[types.Part(text="""You are a professional AI assistant. 
Follow strict rules: No reasoning, No extra text. Provide clean, final answers in structured format (bullet points or numbered steps).""")]
    )

    try:
        response = client.models.generate_content(
            model=target_model,
            contents=_map_messages(messages),
            config=config
        )

        # Extract tools safely
        tool_calls = None
        if response.candidates[0].content.parts:
            parts = response.candidates[0].content.parts
            google_calls = [p.function_call for p in parts if p.function_call]
            if google_calls:
                tool_calls = [type('TC', (), {
                    'id': f"call_{c.name}_{i}",
                    'function': type('F', (), {'name': c.name, 'arguments': json.dumps(c.args or {})}),
                    'type': 'function'
                }) for i, c in enumerate(google_calls)]

        # Extract text safely
        text = ""
        try:
            text = response.text
        except (AttributeError, ValueError):
            if response.candidates[0].content.parts:
                text = response.candidates[0].content.parts[0].text or ""

        return MockResponse(text, tool_calls, model=target_model)

    except Exception as e:
        if "404" in str(e) and target_model == DEFAULT_MODEL:
            return await call_llm(messages, tools, MODEL_NAME, tool_choice)
        raise e
