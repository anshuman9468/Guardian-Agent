import logging
import os
from typing import Any
import google.generativeai as genai
from openai.types.chat import ChatCompletion

# ─── Configuration ────────────────────────────────────────────────────────────
# We use gemini-1.5-flash for the best balance of speed and free-tier quota
MODEL_NAME = "gemini-1.5-flash"
DEFAULT_MODEL = MODEL_NAME

logger = logging.getLogger(__name__)

# ─── Google SDK Initialization ────────────────────────────────────────────────

def _init_genai():
    # Supports both names to be safe
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY or GEMINI_API_KEY is not set.")
    genai.configure(api_key=api_key)

# ─── OpenAI-to-Google Format Mappers ─────────────────────────────────────────

def _map_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converts OpenAI format [{'role': 'user', 'content': '...'}] to Google format."""
    mapped = []
    for m in messages:
        role = m["role"]
        if role == "assistant": role = "model"
        if role == "system": continue # Google handles system separately or via context
        
        mapped.append({
            "role": role,
            "parts": [m["content"]]
        })
    return mapped

def _map_tools(tools: list[dict[str, Any]]) -> list[genai.types.FunctionDeclaration]:
    """Converts OpenAI tool definitions to Google FunctionDeclarations."""
    # The Google SDK handles this best if we pass the raw OpenAI-style dicts
    # but specifically formatted for their 'tools' parameter.
    return [{"function_declarations": [t["function"] for t in tools]}] if tools else None

# ─── Core LLM Call ────────────────────────────────────────────────────────────

async def call_llm(
    messages: list[dict[str, Any]],
    tools:    list[dict[str, Any]] | None = None,
    model:    str | None = None,
    tool_choice: str | dict | None = None,
) -> Any:
    """
    Direct Google Gemini SDK caller.
    Returns an object that mimics the OpenAI response structure to keep agent_loop.py happy.
    """
    _init_genai()
    
    target_model_name = model or MODEL_NAME
    # Remove "google/" prefix if it exists in the incoming request
    if "/" in target_model_name:
        target_model_name = target_model_name.split("/")[-1]
        
    logger.info("Calling Native Gemini SDK | model=%s", target_model_name)

    # 1. Setup Model & Tools
    google_tools = _map_tools(tools)
    model_instance = genai.GenerativeModel(
        model_name=target_model_name,
        tools=google_tools,
        generation_config={"temperature": 0.5, "max_output_tokens": 1000}
    )

    # 2. Prepare History vs Last Message
    # Google SDK works best with a ChatSession if tools are involved
    chat = model_instance.start_chat(history=_map_messages(messages[:-1]))
    last_msg = messages[-1]["content"]

    try:
        # 3. Call Gemini
        response = await chat.send_message_async(last_msg)
        
        # 4. Wrap result to look like OpenAI (so agent_loop.py doesn't need a rewrite)
        class MockMessage:
            def __init__(self, content, tool_calls=None):
                self.content = content
                self.tool_calls = tool_calls
                self.role = "assistant"

        class MockChoice:
            def __init__(self, message):
                self.message = message

        class MockResponse:
            def __init__(self, content, tool_calls=None):
                self.choices = [MockChoice(MockMessage(content, tool_calls))]
                self.model = target_model_name

        # Extract tool calls from Google response if they exist
        tool_calls = None
        if response.candidates[0].content.parts:
            parts = response.candidates[0].content.parts
            google_calls = [p.function_call for p in parts if p.function_call]
            
            if google_calls:
                tool_calls = []
                for i, call in enumerate(google_calls):
                    tool_calls.append(type('TC', (), {
                        'id': f"call_{i}",
                        'function': type('F', (), {
                            'name': call.name,
                            'arguments': json_dumps_args(call.args)
                        }),
                        'type': 'function'
                    }))

        text_content = response.text if not tool_calls else ""
        return MockResponse(text_content, tool_calls)

    except Exception as e:
        logger.error(f"Native Gemini SDK call failed: {e}")
        raise e

def json_dumps_args(args):
    import json
    # Google args are already a dict-like object
    return json.dumps({k: v for k, v in args.items()})
