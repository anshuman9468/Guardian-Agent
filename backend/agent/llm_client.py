import logging
import os
import json
from typing import Any
from google import genai
from google.genai import types

# ─── Configuration ────────────────────────────────────────────────────────────
MODEL_NAME = "gemini-2.0-flash-lite-preview-02-05" # Real ID for 2.5 series
DEFAULT_MODEL = "gemini-2.5-flash-lite" # User-requested ID

logger = logging.getLogger(__name__)

# ─── New Google GenAI Client ──────────────────────────────────────────────────

def _get_client():
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY is not set in Render environment.")
    return genai.Client(api_key=api_key)

# ─── Format Mappers ──────────────────────────────────────────────────────────

def _map_messages(messages: list[dict[str, Any]]) -> list[types.Content]:
    """Maps OpenAI messages to new Google SDK Content types."""
    mapped = []
    for m in messages:
        role = m["role"]
        if role == "assistant": role = "model"
        if role == "system": continue # Handled differently in config
        
        mapped.append(types.Content(
            role=role,
            parts=[types.Part(text=m["content"])]
        ))
    return mapped

def _map_tools(tools: list[dict[str, Any]]) -> list[types.Tool]:
    """Maps OpenAI tools to new Google SDK Tool types."""
    if not tools: return None
    
    declarations = []
    for t in tools:
        fn = t["function"]
        declarations.append(types.FunctionDeclaration(
            name=fn["name"],
            description=fn.get("description", ""),
            parameters=fn.get("parameters", {"type": "object", "properties": {}})
        ))
    
    return [types.Tool(function_declarations=declarations)]

# ─── Core LLM Call ────────────────────────────────────────────────────────────

async def call_llm(
    messages: list[dict[str, Any]],
    tools:    list[dict[str, Any]] | None = None,
    model:    str | None = None,
    tool_choice: str | dict | None = None,
) -> Any:
    """
    Newest Google GenAI SDK caller.
    Maintains OpenAI-like response object for agent_loop.py compatibility.
    """
    client = _get_client()
    
    # Use user model or the latest 2.0/2.5 preview
    target_model = model or DEFAULT_MODEL
    # Strip any prefixes
    if "/" in target_model: target_model = target_model.split("/")[-1]
    
    logger.info("Calling NEW Google GenAI SDK | model=%s", target_model)

    # 1. Prepare Config
    config = types.GenerateContentConfig(
        tools=_map_tools(tools),
        temperature=0.5,
        max_output_tokens=1000,
        system_instruction=[types.Part(text="You are a helpful assistant with access to tools.") ]
    )

    try:
        # 2. Call Gemini
        # The new SDK is sync by default but supports threading; 
        # using the standard call for simplicity as it's the fastest path.
        response = client.models.generate_content(
            model=target_model,
            contents=_map_messages(messages),
            config=config
        )

        # 3. Adapter to keep agent_loop.py happy
        class MockMessage:
            def __init__(self, content, tool_calls=None):
                self.content = content or ""
                self.tool_calls = tool_calls
                self.role = "assistant"

        class MockChoice:
            def __init__(self, message):
                self.message = message

        class MockResponse:
            def __init__(self, content, tool_calls=None):
                self.choices = [MockChoice(MockMessage(content, tool_calls))]
                self.model = target_model

        # 4. Extract Tool Calls
        tool_calls = None
        if response.candidates[0].content.parts:
            parts = response.candidates[0].content.parts
            google_calls = [p.function_call for p in parts if p.function_call]
            
            if google_calls:
                tool_calls = []
                for i, call in enumerate(google_calls):
                    # Wrap in an object that looks like OpenAI's tool_call
                    tool_calls.append(type('TC', (), {
                        'id': f"call_{call.name}_{i}",
                        'function': type('F', (), {
                            'name': call.name,
                            'arguments': json.dumps(call.args if call.args else {})
                        }),
                        'type': 'function'
                    }))

        text_content = response.text if not tool_calls else ""
        return MockResponse(text_content, tool_calls)

    except Exception as e:
        # Fallback to the real ID if the requested one fails
        if target_model == DEFAULT_MODEL and "404" in str(e):
            logger.warning(f"Model {target_model} not found, retrying with {MODEL_NAME}")
            return await call_llm(messages, tools, MODEL_NAME, tool_choice)
            
        logger.error(f"NEW Gemini SDK call failed: {e}")
        raise e
