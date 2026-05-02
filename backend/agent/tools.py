"""
tools.py — Tool registry: definitions + executor.

Includes hardcoded test tools and HTTP wrappers for the detached
filesystem, fetch, github, and sqlite services.
"""

from __future__ import annotations

import datetime
import logging
import httpx
import os
from typing import Any

from mcp_servers.server_registry import MCP_SERVERS

logger = logging.getLogger(__name__)

# ─── GitHub direct API (avoid flaky external MCP) ─────────────────────────────

GITHUB_API = "https://api.github.com"


def _github_headers() -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "GuardianAgent/1.0",
    }
    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def _github_get(path: str, params: dict[str, Any] | None = None) -> httpx.Response:
    url = f"{GITHUB_API}{path}"
    async with httpx.AsyncClient(timeout=15) as client:
        return await client.get(url, headers=_github_headers(), params=params)


def _format_open_issues(owner: str, repo: str, issues: list[dict[str, Any]]) -> str:
    if not issues:
        return f"✅ No open issues found in `{owner}/{repo}`."

    lines = [f"Open issues in `{owner}/{repo}` (showing {len(issues)}):"]
    for i, issue in enumerate(issues, 1):
        labels = issue.get("labels") or []
        label_names = [l.get("name") for l in labels if isinstance(l, dict) and l.get("name")]
        label_str = ", ".join(label_names) if label_names else "none"
        url = issue.get("html_url", "")
        lines.append(f"{i}. #{issue.get('number')} — {issue.get('title')}\n   labels: {label_str}\n   url: {url}")
    return "\n".join(lines)

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
                    # Never dump raw HTML into the agent chat.
                    content_type = (res.headers.get("content-type") or "").lower()
                    body = res.text or ""
                    if "text/html" in content_type or body.lstrip().lower().startswith("<!doctype html") or body.lstrip().lower().startswith("<html"):
                        return f"HTTP {res.status_code}: upstream service returned HTML (unavailable)."
                    return f"HTTP {res.status_code}: {body[:5000]}"
            
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
    owner = args["owner"]
    repo = args["repo"]
    r = await _github_get(f"/repos/{owner}/{repo}")
    if r.status_code == 404:
        return f"Error: Repository `{owner}/{repo}` not found."
    if r.status_code == 403:
        return "Error: GitHub rate limit reached. Set `GITHUB_TOKEN`."
    r.raise_for_status()
    d = r.json()
    return (
        f"{d.get('full_name')}\n"
        f"- description: {d.get('description') or 'N/A'}\n"
        f"- language: {d.get('language') or 'N/A'}\n"
        f"- stars: {d.get('stargazers_count')}\n"
        f"- forks: {d.get('forks_count')}\n"
        f"- open_issues_count: {d.get('open_issues_count')}\n"
        f"- url: {d.get('html_url')}"
    )

async def _handle_list_open_issues(args: dict[str, Any]) -> str:
    owner = args["owner"]
    repo = args["repo"]
    limit = int(args.get("limit", 5) or 5)
    limit = min(max(limit, 1), 10)

    r = await _github_get(
        f"/repos/{owner}/{repo}/issues",
        params={"state": "open", "per_page": 30, "sort": "created", "direction": "desc"},
    )
    if r.status_code == 404:
        return f"Error: Repository `{owner}/{repo}` not found."
    if r.status_code == 403:
        return "Error: GitHub rate limit reached. Set `GITHUB_TOKEN`."
    r.raise_for_status()

    raw = r.json()
    issues = [i for i in raw if isinstance(i, dict) and "pull_request" not in i][:limit]
    return _format_open_issues(owner, repo, issues)

async def _handle_get_repo_languages(args: dict[str, Any]) -> str:
    owner = args["owner"]
    repo = args["repo"]
    r = await _github_get(f"/repos/{owner}/{repo}/languages")
    if r.status_code == 404:
        return f"Error: Repository `{owner}/{repo}` not found."
    if r.status_code == 403:
        return "Error: GitHub rate limit reached. Set `GITHUB_TOKEN`."
    r.raise_for_status()
    langs = r.json() or {}
    if not langs:
        return f"No language data available for `{owner}/{repo}`."
    total = sum(langs.values()) or 1
    lines = [f"Language breakdown for `{owner}/{repo}`:"]
    for lang, count in sorted(langs.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        lines.append(f"- {lang}: {pct:.1f}%")
    return "\n".join(lines)

async def _handle_search_repos(args: dict[str, Any]) -> str:
    query = args["query"]
    limit = int(args.get("limit", 5) or 5)
    limit = min(max(limit, 1), 10)
    r = await _github_get("/search/repositories", params={"q": query, "sort": "stars", "order": "desc", "per_page": limit})
    if r.status_code == 403:
        return "Error: GitHub rate limit reached. Set `GITHUB_TOKEN`."
    r.raise_for_status()
    data = r.json() or {}
    items = data.get("items") or []
    if not items:
        return f"No repositories found for query: `{query}`"
    lines = [f"GitHub search `{query}` (showing {min(limit, len(items))}):"]
    for i, repo in enumerate(items[:limit], 1):
        lines.append(f"{i}. {repo.get('full_name')} — ⭐ {repo.get('stargazers_count')} — {repo.get('html_url')}")
    return "\n".join(lines)

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
