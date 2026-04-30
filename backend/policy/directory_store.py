import os
from typing import List

# The absolute safest root we allow. The agent can never escape this.
SAFE_BASE = "/home/anshumandutta"

# Initial allowed directories. We default to the sandbox.
_allowed_dirs: List[str] = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "guardian-sandbox"))
]

def get_allowed_dirs() -> List[str]:
    return list(_allowed_dirs)

def add_allowed_dir(path: str) -> dict[str, str]:
    abs_path = os.path.abspath(path.strip())
    
    if not abs_path.startswith(SAFE_BASE):
        return {"status": "error", "message": f"Path must be within {SAFE_BASE}"}
    
    if abs_path in _allowed_dirs:
        return {"status": "error", "message": "Directory is already allowed"}
        
    _allowed_dirs.append(abs_path)
    return {"status": "ok", "message": f"Added {abs_path} to allowed directories"}

def remove_allowed_dir(path: str) -> dict[str, str]:
    abs_path = os.path.abspath(path.strip())
    if abs_path in _allowed_dirs:
        _allowed_dirs.remove(abs_path)
        return {"status": "ok", "message": f"Removed {abs_path}"}
    return {"status": "error", "message": "Directory not found in allowed list"}

def is_path_allowed(requested_path: str) -> bool:
    """Check if the requested path falls under ANY of the allowed directories."""
    abs_req = os.path.abspath(requested_path)
    return any(abs_req.startswith(d) for d in _allowed_dirs)
