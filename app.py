import os
import json
import base64
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Response

# -----------------------------
# Config
# -----------------------------
GITHUB_API = "https://api.github.com"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
DEFAULT_REPO = os.getenv("DEFAULT_REPO", "").strip()          # "owner/repo"
DEFAULT_BRANCH = os.getenv("DEFAULT_BRANCH", "main").strip()
SERVICE_NAME = os.getenv("SERVICE_NAME", "ida-mcp-gateway").strip()
VERSION = os.getenv("VERSION", "2.0.0").strip()

app = FastAPI(title=SERVICE_NAME, version=VERSION)

# -----------------------------
# CORS (required for Builder/Hoppscotch in browser)
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # keep simple for now
    allow_credentials=False,      # wildcard origins + credentials is problematic
    allow_methods=["*"],
    allow_headers=["*"],
)

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


def get_repo(args: Dict[str, Any]) -> str:
    return (args.get("repo") or DEFAULT_REPO or "").strip()


def get_ref(args: Dict[str, Any]) -> str:
    return (args.get("ref") or DEFAULT_BRANCH or "").strip()


# -----------------------------
# Tools (business logic)
# -----------------------------
def tool_health_check(_args: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "message": "IDA MCP Gateway alive ✅",
        "service": SERVICE_NAME,
        "version": VERSION,
        "ts": utc_iso(),
        "defaults": {"repo": DEFAULT_REPO or None, "ref": DEFAULT_BRANCH},
    }


def tool_github_read_file(args: Dict[str, Any]) -> Dict[str, Any]:
    err = require_github_token()
    if err:
        return {"ok": False, "error": err}

    path = (args.get("path") or "").strip()
    if not path:
        return {"ok": False, "error": "Missing required input: path"}

    repo = get_repo(args)
    if not repo:
        return {"ok": False, "error": "No repo provided and DEFAULT_REPO is not set"}

    ref = get_ref(args)
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"

    r = requests.get(url, headers=gh_headers(), params={"ref": ref}, timeout=30)
    if r.status_code != 200:
        return {
            "ok": False,
            "error": "GitHub read failed",
            "status": r.status_code,
            "details": safe_json(r),
        }

    data = r.json()
    content_b64 = data.get("content", "") or ""
    try:
        decoded = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception:
        decoded = ""

    return {
        "ok": True,
        "repo": repo,
        "ref": ref,
        "path": path,
        "sha": data.get("sha"),
        "text": decoded,
    }


def tool_github_write_file(args: Dict[str, Any]) -> Dict[str, Any]:
    err = require_github_token()
    if err:
        return {"ok": False, "error": err}

    path = (args.get("path") or "").strip()
    content = args.get("content")
    message = (args.get("message") or f"Update {path}").strip()

    if not path:
        return {"ok": False, "error": "Missing required input: path"}
    if content is None:
        return {"ok": False, "error": "Missing required input: content"}

    repo = get_repo(args)
    if not repo:
        return {"ok": False, "error": "No repo provided and DEFAULT_REPO is not set"}

    ref = get_ref(args)
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"

    # fetch existing sha (if present)
    existing_sha = None
    get_r = requests.get(url, headers=gh_headers(), params={"ref": ref}, timeout=30)
    if get_r.status_code == 200:
        try:
            existing_sha = get_r.json().get("sha")
        except Exception:
            existing_sha = None

    body = {
        "message": message,
        "content": base64.b64encode(str(content).encode("utf-8")).decode("utf-8"),
        "branch": ref,
    }
    if existing_sha:
        body["sha"] = existing_sha

    put_r = requests.put(url, headers=gh_headers(), data=json.dumps(body), timeout=30)
    if put_r.status_code not in (200, 201):
        return {
            "ok": False,
            "error": "GitHub write failed",
            "status": put_r.status_code,
            "details": safe_json(put_r),
        }

    out = put_r.json()
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


# -----------------------------
# MCP tool registry + schemas
# -----------------------------
TOOLS: Dict[str, Dict[str, Any]] = {
    "health_check": {
        "description": "Simple health check.",
        "inputSchema": {"type": "object", "additionalProperties": True, "properties": {}},
        "handler": tool_health_check,
    },
    "github_read_file": {
        "description": "Read a file from a GitHub repo (returns raw text). If repo/ref omitted, server uses DEFAULT_REPO/DEFAULT_BRANCH.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "path": {"type": "string", "description": "Path in repo, e.g. README.md"},
                "repo": {"type": "string", "description": "owner/repo (optional)"},
                "ref": {"type": "string", "description": "branch/tag/sha (optional, default main)"},
            },
            "required": ["path"],
        },
        "handler": tool_github_read_file,
    },
    "github_write_file": {
        "description": "Create or update a file in a GitHub repo and commit it. If repo/ref omitted, server uses DEFAULT_REPO/DEFAULT_BRANCH.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "path": {"type": "string", "description": "Path in repo, e.g. agent_outbox/bridge_test.txt"},
                "content": {"type": "string", "description": "File content (utf-8 string)"},
                "message": {"type": "string", "description": "Commit message (optional)"},
                "repo": {"type": "string", "description": "owner/repo (optional)"},
                "ref": {"type": "string", "description": "branch/tag/sha (optional, default main)"},
            },
            "required": ["path", "content"],
        },
        "handler": tool_github_write_file,
    },
}


def mcp_error(req_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def mcp_result(req_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


# -----------------------------
# Public endpoints (debug)
# -----------------------------
@app.get("/")
@app.head("/")
def root():
    return tool_health_check({})


@app.get("/health")
@app.head("/health")
def health():
    return tool_health_check({})


# -----------------------------
# MCP JSON-RPC endpoint
# Builder expects POST /mcp with methods:
# - initialize
# - tools/list
# - tools/call
# Also: browser clients require OPTIONS preflight.
# -----------------------------
@app.options("/mcp")
def mcp_options():
    # CORS middleware will add headers, this just ensures 200 OK for preflight.
    return Response(status_code=200)


@app.post("/mcp")
async def mcp(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(mcp_error(None, -32700, "Parse error: invalid JSON"), status_code=400)

    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}

    if body.get("jsonrpc") != "2.0" or not method:
        return JSONResponse(mcp_error(req_id, -32600, "Invalid Request"), status_code=400)

    # 1) initialize
    if method == "initialize":
        result = {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "serverInfo": {"name": SERVICE_NAME, "version": VERSION},
            "capabilities": {"tools": {"listChanged": False}},
        }
        return JSONResponse(mcp_result(req_id, result))

    # 2) tools/list
    if method in ("tools/list", "listTools"):
        tools_list = [
            {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
            for name, spec in TOOLS.items()
        ]
        return JSONResponse(mcp_result(req_id, {"tools": tools_list}))

    # 3) tools/call
    if method in ("tools/call", "callTool"):
        name = params.get("name") or params.get("tool")
        args = params.get("arguments") or params.get("input") or {}

        if not name or name not in TOOLS:
            return JSONResponse(mcp_error(req_id, -32602, "Unknown tool", {"name": name}), status_code=400)

        handler = TOOLS[name]["handler"]
        try:
            out = handler(args if isinstance(args, dict) else {})
        except Exception as e:
            return JSONResponse(mcp_error(req_id, -32000, "Tool execution failed", {"error": str(e)}), status_code=500)

        # MCP expects content array. Keep it predictable.
        result = {
            "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
            "isError": bool(out.get("ok") is False),
        }
        return JSONResponse(mcp_result(req_id, result))

    return JSONResponse(mcp_error(req_id, -32601, f"Method not found: {method}"), status_code=400)
