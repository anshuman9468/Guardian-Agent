"""
github_server.py — Custom MCP server for GitHub repo analysis.

Tools:
  1. get_repo_info(owner, repo)          — stars, forks, language, description
  2. list_open_issues(owner, repo)       — latest open issues with labels
  3. get_repo_languages(owner, repo)     — language % breakdown
  4. search_repos(query)                 — search GitHub for repos

Run standalone:
  python custom_mcp/github_server.py

Registered in server_registry.py as a stdio MCP server.
GITHUB_TOKEN is optional but raises rate limit from 60 → 5000 req/hr.
"""

from __future__ import annotations

import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

# ── Setup ─────────────────────────────────────────────────────────────────────

mcp = FastMCP("github-analyzer")

GITHUB_API = "https://api.github.com"

def _headers() -> dict[str, str]:
    """Build request headers. Adds auth token if set in environment."""
    h = {
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent":           "GuardianAgent/1.0",
    }
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


# ── Tool 1: get_repo_info ─────────────────────────────────────────────────────

@mcp.tool()
async def get_repo_info(owner: str, repo: str) -> str:
    """
    Get detailed information about a GitHub repository.

    Args:
        owner: GitHub username or organisation (e.g. 'microsoft').
        repo:  Repository name (e.g. 'vscode').

    Returns:
        Formatted summary with stars, forks, language, description, and more.
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers())

    if r.status_code == 404:
        return f"❌ Repository '{owner}/{repo}' not found."
    if r.status_code == 403:
        return "❌ GitHub rate limit reached. Set GITHUB_TOKEN in .env to increase limit."
    r.raise_for_status()

    d = r.json()
    license_name = (d.get("license") or {}).get("name", "None")
    topics       = ", ".join(d.get("topics", [])) or "None"

    return (
        f"📦 {d['full_name']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 Description : {d.get('description') or 'N/A'}\n"
        f"🌐 Homepage    : {d.get('homepage') or 'N/A'}\n"
        f"💻 Language    : {d.get('language') or 'N/A'}\n"
        f"⭐ Stars       : {d['stargazers_count']:,}\n"
        f"🍴 Forks       : {d['forks_count']:,}\n"
        f"🐛 Open Issues : {d['open_issues_count']:,}\n"
        f"👁️  Watchers    : {d['watchers_count']:,}\n"
        f"📄 License     : {license_name}\n"
        f"🏷️  Topics      : {topics}\n"
        f"📅 Created     : {d['created_at'][:10]}\n"
        f"🔄 Updated     : {d['updated_at'][:10]}\n"
        f"🔗 URL         : {d['html_url']}"
    )


# ── Tool 2: list_open_issues ──────────────────────────────────────────────────

@mcp.tool()
async def list_open_issues(owner: str, repo: str, limit: int = 5) -> str:
    """
    List the most recent open issues in a GitHub repository.

    Args:
        owner: GitHub username or organisation.
        repo:  Repository name.
        limit: Number of issues to return (max 10, default 5).

    Returns:
        Numbered list of open issues with title, number, and labels.
    """
    limit = min(max(limit, 1), 10)
    url   = f"{GITHUB_API}/repos/{owner}/{repo}/issues"
    params = {"state": "open", "per_page": 30, "sort": "created", "direction": "desc"}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers(), params=params)

    if r.status_code == 404:
        return f"❌ Repository '{owner}/{repo}' not found."
    if r.status_code == 403:
        return "❌ GitHub rate limit reached. Set GITHUB_TOKEN in .env."
    r.raise_for_status()

    issues = [i for i in r.json() if "pull_request" not in i]  # exclude PRs
    issues = issues[:limit]
    
    if not issues:
        return f"✅ No open issues found in '{owner}/{repo}'."

    lines = [f"🐛 Open Issues in {owner}/{repo} (showing {len(issues)})\n"]
    for i, issue in enumerate(issues, 1):
        labels = " ".join(f"[{l['name']}]" for l in issue.get("labels", []))
        lines.append(
            f"{i}. #{issue['number']} — {issue['title']}\n"
            f"   Labels: {labels or 'none'}  |  Opened: {issue['created_at'][:10]}"
        )
    return "\n".join(lines)


# ── Tool 3: get_repo_languages ────────────────────────────────────────────────

@mcp.tool()
async def get_repo_languages(owner: str, repo: str) -> str:
    """
    Get the programming language breakdown for a GitHub repository.

    Args:
        owner: GitHub username or organisation.
        repo:  Repository name.

    Returns:
        Language breakdown with byte counts and percentages.
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/languages"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers())

    if r.status_code == 404:
        return f"❌ Repository '{owner}/{repo}' not found."
    r.raise_for_status()

    langs = r.json()
    if not langs:
        return f"No language data available for '{owner}/{repo}'."

    total = sum(langs.values())
    lines = [f"💻 Language breakdown for {owner}/{repo}:\n"]
    for lang, count in sorted(langs.items(), key=lambda x: -x[1]):
        pct   = count / total * 100
        bar   = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        lines.append(f"  {lang:<20} {bar}  {pct:5.1f}%")

    return "\n".join(lines)


# ── Tool 4: search_repos ──────────────────────────────────────────────────────

@mcp.tool()
async def search_repos(query: str, limit: int = 5) -> str:
    """
    Search GitHub for public repositories matching a query.

    Args:
        query: Search terms (e.g. 'python web scraper', 'react dashboard').
        limit: Number of results to return (max 8, default 5).

    Returns:
        List of matching repos with stars, language, and description.
    """
    limit  = min(max(limit, 1), 8)
    url    = f"{GITHUB_API}/search/repositories"
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": limit}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers(), params=params)

    if r.status_code == 403:
        return "❌ GitHub rate limit reached. Set GITHUB_TOKEN in .env."
    r.raise_for_status()

    data  = r.json()
    items = data.get("items", [])
    total = data.get("total_count", 0)

    if not items:
        return f"No repositories found for query: '{query}'"

    lines = [f"🔍 GitHub search: '{query}'  ({total:,} total results, showing {len(items)})\n"]
    for i, repo in enumerate(items, 1):
        lines.append(
            f"{i}. ⭐ {repo['stargazers_count']:>7,}  {repo['full_name']}\n"
            f"   {repo.get('description') or 'No description'}  "
            f"[{repo.get('language') or 'N/A'}]"
        )
    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
