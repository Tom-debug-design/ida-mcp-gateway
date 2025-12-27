import os
import json
import base64
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastmcp import FastMCP  # <— NYTT

# -----------------------------
# Config
# -----------------------------
GITHUB_API = "https://api.github.com"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
DEFAULT_REPO = os.getenv("DEFAULT_REPO", "").strip()          # "owner/repo"
DEFAULT_BRANCH = os.getenv("DEFAULT_BRANCH", "main").strip()
SERVICE_NAME = os.getenv("SERVICE_NAME", "ida-mcp-gateway").strip()
VERSION = os.getenv("VERSION", "2.0.0").strip()

def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def gh_headers() -> Dict[str, str]:
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": SERVICE_NAME,
    }

def safe_json(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {"text": (resp.text or "")[:2000]}

def require_github_token() -> Optional[str]:
    if not GITHUB_TOKEN:
        return "Missing GITHUB_TOKEN env var"
    return None

def get_repo(repo: Optional[str]) -> str:
    return (repo or DEFAULT_REPO or "").strip()

def get_ref(ref: Optional[str]) -> str:
    return (ref or DEFAULT_BRANCH or "").strip()

# -----------------------------
# FastAPI (health + CORS)
# -----------------------------
app = FastAPI(title=SERVICE_NAME, version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "ok": True,
        "message": "IDA MCP Gateway alive ✅",
        "service": SERVICE_NAME,
        "version": VERSION,
        "ts": utc_iso(),
        "defaults": {"repo": DEFAULT_REPO or None, "ref": DEFAULT_BRANCH},
        "mcp_sse": "/sse/",
    }

@app.get("/health")
def health():
    return {"ok": True, "ts": utc_iso(), "service": SERVICE_NAME, "version": VERSION}

# -----------------------------
# MCP over SSE (for Builder)
# -----------------------------
mcp = FastMCP(name=SERVICE_NAME)

@mcp.tool()
async def health_check() -> Dict[str, Any]:
    return {
        "ok": True,
        "message": "IDA MCP Gateway alive ✅",
        "service": SERVICE_NAME,
        "version": VERSION,
        "ts": utc_iso(),
        "defaults": {"repo": DEFAULT_REPO or None, "ref": DEFAULT_BRANCH},
    }

@mcp.tool()
async def github_read_file(path: str, repo: Optional[str] = None, ref: Optional[str] = None) -> Dict[str, Any]:
    err = require_github_token()
    if err:
        return {"ok": False, "error": err}
    if not path:
        return {"ok": False, "error": "Missing required input: path"}

    repo_v = get_repo(repo)
    if not repo_v:
        return {"ok": False, "error": "No repo provided and DEFAULT_REPO is not set"}

    ref_v = get_ref(ref)
    url = f"{GITHUB_API}/repos/{repo_v}/contents/{path}"
    r = requests.get(url, headers=gh_headers(), params={"ref": ref_v}, timeout=30)
    if r.status_code != 200:
        return {"ok": False, "error": "GitHub read failed", "status": r.status_code, "details": safe_json(r)}

    data = r.json()
    content_b64 = data.get("content", "") or ""
    try:
        decoded = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception:
        decoded = ""

    return {"ok": True, "repo": repo_v, "ref": ref_v, "path": path, "sha": data.get("sha"), "text": decoded}

@mcp.tool()
async def github_write_file(
    path: str,
    content: str,
    message: Optional[str] = None,
    repo: Optional[str] = None,
    ref: Optional[str] = None,
) -> Dict[str, Any]:
    err = require_github_token()
    if err:
        return {"ok": False, "error": err}
    if not path:
        return {"ok": False, "error": "Missing required input: path"}

    repo_v = get_repo(repo)
    if not repo_v:
        return {"ok": False, "error": "No repo provided and DEFAULT_REPO is not set"}

    ref_v = get_ref(ref)
    url = f"{GITHUB_API}/repos/{repo_v}/contents/{path}"

    existing_sha = None
    get_r = requests.get(url, headers=gh_headers(), params={"ref": ref_v}, timeout=30)
    if get_r.status_code == 200:
        try:
            existing_sha = get_r.json().get("sha")
        except Exception:
            existing_sha = None

    body = {
        "message": (message or f"Update {path}"),
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": ref_v,
    }
    if existing_sha:
        body["sha"] = existing_sha

    put_r = requests.put(url, headers=gh_headers(), data=json.dumps(body), timeout=30)
    if put_r.status_code not in (200, 201):
        return {"ok": False, "error": "GitHub write failed", "status": put_r.status_code, "details": safe_json(put_r)}

    out = put_r.json()
    return {
        "ok": True,
        "repo": repo_v,
        "ref": ref_v,
        "path": path,
        "commit": (out.get("commit") or {}).get("sha"),
        "content_sha": (out.get("content") or {}).get("sha"),
        "created": (put_r.status_code == 201),
        "updated": (put_r.status_code == 200),
    }

# Mount SSE-endepunkter (gir /sse/)
app.mount("/", mcp.http_app(path="/sse"))
