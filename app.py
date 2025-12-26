import os
import base64
import json
from datetime import datetime, timezone

import requests
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.middleware.cors import CORSMiddleware

# ---------- Config ----------
GITHUB_TOKEN = (os.getenv("GITHUB_TOKEN") or "").strip()
DEFAULT_REPO = (os.getenv("DEFAULT_REPO") or "").strip()          # "owner/repo"
DEFAULT_BRANCH = (os.getenv("DEFAULT_BRANCH") or "main").strip()
SERVICE_NAME = (os.getenv("SERVICE_NAME") or "ida-mcp-gateway").strip()
VERSION = (os.getenv("VERSION") or "2.0.0").strip()

GITHUB_API = "https://api.github.com"

def utc_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def require_github():
    if not GITHUB_TOKEN:
        return "Missing GITHUB_TOKEN"
    return None

def gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ida-mcp-gateway",
    }

def get_repo(args: dict):
    return ((args.get("repo") or DEFAULT_REPO) or "").strip()

def get_ref(args: dict):
    return ((args.get("ref") or DEFAULT_BRANCH) or "").strip()

def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"text": (resp.text or "")[:2000]}

# ---------- MCP Server ----------
# Recommended for production: stateless_http + json_response
mcp = FastMCP(SERVICE_NAME, stateless_http=True, json_response=True)  # streamable-http mounts at /mcp by default :contentReference[oaicite:1]{index=1}

@mcp.tool()
def health_check() -> dict:
    """Health check for the MCP gateway."""
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "version": VERSION,
        "ts": utc_iso(),
        "defaults": {
            "repo": DEFAULT_REPO or None,
            "ref": DEFAULT_BRANCH,
        },
    }

@mcp.tool()
def github_read_file(path: str, repo: str = "", ref: str = "") -> dict:
    """Read a file from a GitHub repo (returns raw text)."""
    err = require_github()
    if err:
        return {"ok": False, "error": err}

    args = {"repo": repo, "ref": ref}
    repo = get_repo(args)
    ref = get_ref(args)

    if not repo:
        return {"ok": False, "error": "No repo provided and DEFAULT_REPO not set"}

    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    r = requests.get(url, headers=gh_headers(), params={"ref": ref}, timeout=30)

    if r.status_code != 200:
        return {"ok": False, "error": "GitHub read failed", "status": r.status_code, "details": safe_json(r)}

    data = r.json()
    content_b64 = data.get("content", "") or ""
    try:
        decoded = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception:
        decoded = ""

    return {"ok": True, "repo": repo, "ref": ref, "path": path, "sha": data.get("sha"), "text": decoded}

@mcp.tool()
def github_write_file(path: str, content: str, message: str = "", repo: str = "", ref: str = "") -> dict:
    """Create/update a file in a GitHub repo and commit it."""
    err = require_github()
    if err:
        return {"ok": False, "error": err}

    args = {"repo": repo, "ref": ref}
    repo = get_repo(args)
    ref = get_ref(args)

    if not repo:
        return {"ok": False, "error": "No repo provided and DEFAULT_REPO not set"}

    if not message:
        message = f"Update {path}"

    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"

    # Get existing SHA if file exists
    existing_sha = None
    get_r = requests.get(url, headers=gh_headers(), params={"ref": ref}, timeout=30)
    if get_r.status_code == 200:
        existing_sha = (get_r.json() or {}).get("sha")

    body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": ref,
    }
    if existing_sha:
        body["sha"] = existing_sha

    put_r = requests.put(url, headers=gh_headers(), data=json.dumps(body), timeout=30)

    if put_r.status_code not in (200, 201):
        return {"ok": False, "error": "GitHub write failed", "status": put_r.status_code, "details": safe_json(put_r)}

    out = put_r.json() or {}
    return {
        "ok": True,
        "repo": repo,
        "ref": ref,
        "path": path,
        "commit": (out.get("commit") or {}).get("sha"),
        "content_sha": (out.get("content") or {}).get("sha"),
        "created": (put_r.status_code == 201),
        "updated": (put_r.status_code == 200),
    }

# ---------- ASGI app (Render-friendly) ----------
# Mount MCP streamable-http app at "/"
# Clients will connect to https://<your-domain>/mcp  :contentReference[oaicite:2]{index=2}
asgi_app = Starlette(routes=[Mount("/", app=mcp.streamable_http_app())])

# CORS: needed for browser-based clients; harmless for Builder too :contentReference[oaicite:3]{index=3}
app = CORSMiddleware(
    asgi_app,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id"],
)
