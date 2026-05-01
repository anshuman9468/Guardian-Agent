from fastapi import FastAPI
import httpx

app = FastAPI()

@app.get("/fetch")
async def fetch(url: str):
    # Added https fallback logic here just in case as requested earlier
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    async with httpx.AsyncClient() as client:
        res = await client.get(url)
        return {"content": res.text}
