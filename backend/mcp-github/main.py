from fastapi import FastAPI
import httpx
import os

app = FastAPI()
TOKEN = os.getenv("GITHUB_TOKEN")

headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

@app.get("/repo")
async def get_repo(owner: str, repo: str):
    url = f"https://api.github.com/repos/{owner}/{repo}"
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers)
        return res.json()
