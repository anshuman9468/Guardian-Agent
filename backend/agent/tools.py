"""
tools.py — Tool registry: definitions + executor.

Includes hardcoded test tools and HTTP wrappers for the detached
filesystem, fetch, github, and sqlite services.
"""

from __future__ import annotations

import datetime
import logging
import httpx
from typing import Any

from mcp_servers.server_registry import MCP_SERVERS

logger = logging.getLogger(__name__)

# ─── Tool definitions (OpenAI function-calling schema) ───────────────────────

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Returns the current local date and time. Use this whenever the user asks what time or date it is.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "echo",
            "description": "Echoes back the provided text. Useful for testing the tool pipeline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to echo back."}
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
    # Filesystem Service Tools
    {
        "type": "function",
        "_server": "filesystem",
        "function": {
            "name": "read_file",
            "description": "Read a file from the filesystem.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Absolute path to the file."}},
                "required": ["path"]
            }
        }
    },
    # Fetch Service Tools
    {
        "type": "function",
        "_server": "fetch",
        "function": {
            "name": "fetch",
            "description": "Fetch content from a URL.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL to fetch content from."}},
                "required": ["url"]
            }
        }
    },
    # GitHub Service Tools
    {
        "type": "function",
        "_server": "github",
        "function": {
            "name": "get_repo_info",
            "description": "Get detailed information about a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "GitHub username or organisation."},
                    "repo": {"type": "string", "description": "Repository name."}
                },
                "required": ["owner", "repo"]
            }
        }
    },
    {
        "type": "function",
        "_server": "github",
        "function": {
            "name": "list_open_issues",
            "description": "List the most recent open issues in a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "GitHub username or organisation."},
                    "repo": {"type": "string", "description": "Repository name."},
                    "limit": {"type": "integer", "description": "Number of issues to return (max 10)."}
                },
                "required": ["owner", "repo"]
            }
        }
    },
    {
        "type": "function",
        "_server": "github",
        "function": {
            "name": "get_repo_languages",
            "description": "Get the programming language breakdown for a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "GitHub username or organisation."},
                    "repo": {"type": "string", "description": "Repository name."}
                },
                "required": ["owner", "repo"]
            }
        }
    },
    {
        "type": "function",
        "_server": "github",
        "function": {
            "name": "search_repos",
            "description": "Search GitHub for public repositories matching a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search terms."},
                    "limit": {"type": "integer", "description": "Number of results."}
                },
                "required": ["query"]
            }
        }
    },
    # SQLite Service Tools
    {
        "type": "function",
        "_server": "sqlite",
        "function": {
            "name": "create_note",
            "description": "Create a new note or update an existing one in the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The title of the note. Must be unique."},
                    "content": {"type": "string", "description": "The body of the note."}
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "_server": "sqlite",
        "function": {
            "name": "read_note",
            "description": "Read the contents of a specific note by title.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The exact title of the note."}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "_server": "sqlite",
        "function": {
            "name": "search_notes",
            "description": "Search the database for notes containing a specific keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "The word or phrase to search for."}
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "_server": "sqlite",
        "function": {
            "name": "list_notes",
            "description": "List the titles of all notes currently stored in the database.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "_server": "sqlite",
        "function": {
            "name": "delete_note",
            "description": "Delete a note from the database by its title.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The exact title of the note."}
                },
                "required": ["title"]
            }
        }
    }
]


# ─── Generic HTTP Caller ─────────────────────────────────────────────────────

async def _call_http_tool(server: str, endpoint: str, method: str = "GET", params: dict = None, json_data: dict = None) -> str:
    base_url = MCP_SERVERS.get(server)
    if not base_url:
        return f"Error: Server '{server}' not configured in server_registry.py."
    
    url = f"{base_url}{endpoint}"
    try:
        async with httpx.AsyncClient() as client:
            if method == "GET":
                res = await client.get(url, params=params, timeout=10)
            elif method == "POST":
                res = await client.post(url, json=json_data, timeout=10)
            elif method == "DELETE":
                res = await client.delete(url, params=params, timeout=10)
            else:
                return f"Error: Unsupported method {method}"
            
            if res.status_code != 200:
                try:
                    return str(res.json())
                except:
                    return f"HTTP {res.status_code}: {res.text}"
            
            data = res.json()
            # Try to return 'text' or 'content' if it's a dict, else return the whole thing
            if isinstance(data, dict):
                return str(data.get("text", data.get("content", data.get("error", data))))
            return str(data)
    except Exception as e:
        return f"Error connecting to {server}: {e}"


# ─── Tool handler implementations ────────────────────────────────────────────

async def _handle_get_time(_args: dict[str, Any]) -> str:
    now = datetime.datetime.now()
    return now.strftime("Current date and time: %A, %B %d, %Y at %I:%M:%S %p")

async def _handle_echo(args: dict[str, Any]) -> str:
    text = args.get("text", "")
    return f"Echo: {text}"

async def _handle_add_numbers(args: dict[str, Any]) -> str:
    try:
        a = float(args["a"])
        b = float(args["b"])
        return f"{a} + {b} = {a + b}"
    except (KeyError, TypeError, ValueError) as exc:
        return f"Error: {exc}"

# Filesystem
async def _handle_read_file(args: dict[str, Any]) -> str:
    return await _call_http_tool("filesystem", "/filesystem/read", params={"path": args["path"]})

# Fetch
async def _handle_fetch(args: dict[str, Any]) -> str:
    return await _call_http_tool("fetch", "/fetch", params={"url": args["url"]})

# GitHub
async def _handle_get_repo_info(args: dict[str, Any]) -> str:
    return await _call_http_tool("github", "/github/repo", params={"owner": args["owner"], "repo": args["repo"]})

async def _handle_list_open_issues(args: dict[str, Any]) -> str:
    return await _call_http_tool("github", "/github/issues", params={"owner": args["owner"], "repo": args["repo"], "limit": args.get("limit", 5)})

async def _handle_get_repo_languages(args: dict[str, Any]) -> str:
    return await _call_http_tool("github", "/github/languages", params={"owner": args["owner"], "repo": args["repo"]})

async def _handle_search_repos(args: dict[str, Any]) -> str:
    return await _call_http_tool("github", "/github/search", params={"query": args["query"], "limit": args.get("limit", 5)})

# SQLite
async def _handle_create_note(args: dict[str, Any]) -> str:
    return await _call_http_tool("sqlite", "/sqlite/notes/create", method="POST", json_data={"title": args["title"], "content": args["content"]})

async def _handle_read_note(args: dict[str, Any]) -> str:
    return await _call_http_tool("sqlite", "/sqlite/notes/read", params={"title": args["title"]})

async def _handle_search_notes(args: dict[str, Any]) -> str:
    return await _call_http_tool("sqlite", "/sqlite/notes/search", params={"keyword": args["keyword"]})

async def _handle_list_notes(args: dict[str, Any]) -> str:
    return await _call_http_tool("sqlite", "/sqlite/notes/list")

async def _handle_delete_note(args: dict[str, Any]) -> str:
    return await _call_http_tool("sqlite", "/sqlite/notes/delete", method="DELETE", params={"title": args["title"]})


_TOOL_HANDLERS: dict[str, Any] = {
    "get_time": _handle_get_time,
    "echo": _handle_echo,
    "add_numbers": _handle_add_numbers,
    "read_file": _handle_read_file,
    "fetch": _handle_fetch,
    "get_repo_info": _handle_get_repo_info,
    "list_open_issues": _handle_list_open_issues,
    "get_repo_languages": _handle_get_repo_languages,
    "search_repos": _handle_search_repos,
    "create_note": _handle_create_note,
    "read_note": _handle_read_note,
    "search_notes": _handle_search_notes,
    "list_notes": _handle_list_notes,
    "delete_note": _handle_delete_note,
}


# ─── Public executor ─────────────────────────────────────────────────────────

async def tool_executor(tool_name: str, args: dict[str, Any]) -> str:
    """
    Dispatch a tool call to the correct handler.
    """
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        logger.warning("Unknown tool requested: %s", tool_name)
        return (
            f"Tool '{tool_name}' is not available. "
            f"Available tools: {', '.join(_TOOL_HANDLERS.keys())}"
        )

    logger.debug("Executing tool: %s | args: %s", tool_name, args)
    try:
        return await handler(args)
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")
        return f"Error executing tool {tool_name}: {e}"
