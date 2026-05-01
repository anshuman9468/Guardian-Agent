from fastapi import FastAPI, HTTPException
import os

app = FastAPI()

BASE_DIR = "/opt/render/project/src"  # safe root

def is_safe_path(path):
    return os.path.abspath(path).startswith(BASE_DIR)

@app.get("/read_file")
def read_file(path: str):
    if not is_safe_path(path):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    with open(path, "r") as f:
        return {"content": f.read()}
