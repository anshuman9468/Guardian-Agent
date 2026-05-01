"""
github_server.py — Standalone FastAPI service for GitHub repo analysis.

Run standalone:
  uvicorn custom_mcp.github_server:app --host 0.0.0.0 --port 10001
"""

import os
import httpx
from fastapi import FastAPI, HTTPException

app = FastAPI(title="GitHub Service")

GITHUB_API = "https://api.github.com"

def _headers() -> dict[str, str]:
    h = {
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent":           "GuardianAgent/1.0",
    }
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


@app.get("/repo")
async def get_repo_info(owner: str, repo: str):
    url = f"{GITHUB_API}/repos/{owner}/{repo}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers())
    
    if r.status_code == 404:
        return {"error": f"Repository '{owner}/{repo}' not found."}
    if r.status_code == 403:
        return {"error": "GitHub rate limit reached. Set GITHUB_TOKEN in .env."}
    r.raise_for_status()

    d = r.json()
    return {
        "text": (
            f"📦 {d['full_name']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 Description : {d.get('description') or 'N/A'}\n"
            f"🌐 Homepage    : {d.get('homepage') or 'N/A'}\n"
            f"💻 Language    : {d.get('language') or 'N/A'}\n"
            f"⭐ Stars       : {d['stargazers_count']:,}\n"
            f"🍴 Forks       : {d['forks_count']:,}\n"
            f"🐛 Open Issues : {d['open_issues_count']:,}\n"
            f"📄 License     : {(d.get('license') or {}).get('name', 'None')}\n"
            f"🔗 URL         : {d['html_url']}"
        )
    }

@app.get("/issues")
async def list_open_issues(owner: str, repo: str, limit: int = 5):
    limit = min(max(limit, 1), 10)
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues"
    params = {"state": "open", "per_page": 30, "sort": "created", "direction": "desc"}
    
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers(), params=params)

    if r.status_code == 404:
        return {"error": f"Repository '{owner}/{repo}' not found."}
    if r.status_code == 403:
        return {"error": "GitHub rate limit reached."}
    r.raise_for_status()

    issues = [i for i in r.json() if "pull_request" not in i][:limit]
    if not issues:
        return {"text": f"✅ No open issues found in '{owner}/{repo}'."}

    lines = [f"🐛 Open Issues in {owner}/{repo} (showing {len(issues)})\n"]
    for i, issue in enumerate(issues, 1):
        labels = " ".join(f"[{l['name']}]" for l in issue.get("labels", []))
        lines.append(f"{i}. #{issue['number']} — {issue['title']}\n   Labels: {labels or 'none'}")
    return {"text": "\n".join(lines)}

@app.get("/languages")
async def get_repo_languages(owner: str, repo: str):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/languages"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers())

    if r.status_code == 404:
        return {"error": f"Repository '{owner}/{repo}' not found."}
    r.raise_for_status()

    langs = r.json()
    if not langs:
        return {"text": f"No language data available for '{owner}/{repo}'."}

    total = sum(langs.values())
    lines = [f"💻 Language breakdown for {owner}/{repo}:\n"]
    for lang, count in sorted(langs.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        lines.append(f"  {lang:<20} {pct:5.1f}%")
    return {"text": "\n".join(lines)}

@app.get("/search")
async def search_repos(query: str, limit: int = 5):
    limit = min(max(limit, 1), 8)
    url = f"{GITHUB_API}/search/repositories"
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": limit}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers(), params=params)

    if r.status_code == 403:
        return {"error": "GitHub rate limit reached."}
    r.raise_for_status()

    data = r.json()
    items = data.get("items", [])
    if not items:
        return {"text": f"No repositories found for query: '{query}'"}

    lines = [f"🔍 GitHub search: '{query}' (showing {len(items)})\n"]
    for i, repo in enumerate(items, 1):
        lines.append(f"{i}. ⭐ {repo['stargazers_count']:>7,}  {repo['full_name']} - {repo.get('description')}")
    return {"text": "\n".join(lines)}
