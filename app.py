# app.py
import os
import json
import base64
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

APP_VERSION = os.getenv("APP_VERSION", "1.4.0")

# === ENV ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
DEFAULT_REPO = os.getenv("DEFAULT_REPO", "").strip()          # "owner/repo"
DEFAULT_BRANCH = os.getenv("DEFAULT_BRANCH", "main").strip()
GITHUB_API_BASE = os.getenv("GITHUB_API_BASE", "https://api.github.com").strip()

# === Flask ===
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

session = requests.Session()
if GITHUB_TOKEN:
    session.headers.update({
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ida-mcp-gateway",
        "X-GitHub-Api-Version": "2022-11-28",
    })


# ---------------------------
# Helpers
# ---------------------------
def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def require_token() -> Optional[Tuple[Response, int]]:
    if not GITHUB_TOKEN:
        return jsonify({
            "error": "Missing GITHUB_TOKEN",
            "hint": "Set GITHUB_TOKEN in Render Environment Variables"
        }), 500
    return None


def normalize_repo(repo: Optional[str]) -> str:
    repo = (repo or "").strip() or DEFAULT_REPO
    return repo


def normalize_branch(branch: Optional[str]) -> str:
    return (branch or "").strip() or DEFAULT_BRANCH


def gh_get(url: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
    return session.get(url, params=params, timeout=25)


def gh_put(url: str, payload: Dict[str, Any]) -> requests.Response:
    return session.put(url, json=payload, timeout=25)


def gh_contents_url(repo: str, path: str) -> str:
    path = path.lstrip("/")
    return f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}"


def github_read_file(repo: str, path: str, ref: Optional[str] = None) -> str:
    """Return raw text content of a file in GitHub repo."""
    repo = normalize_repo(repo)
    ref = (ref or "").strip()

    if not repo:
        raise ValueError("repo is required (owner/repo)")

    url = gh_contents_url(repo, path)
    params = {}
    if ref:
        params["ref"] = ref

    r = gh_get(url, params=params)
    if r.status_code != 200:
        raise RuntimeError(f"GitHub read failed: {r.status_code} {r.text}")

    data = r.json()
    # GitHub contents API returns base64 content for files
    if isinstance(data, dict) and data.get("type") == "file" and "content" in data:
        content_b64 = data["content"].replace("\n", "")
        raw = base64.b64decode(content_b64).decode("utf-8", errors="replace")
        return raw

    # fallback: if API returns something else
    return json.dumps(data, ensure_ascii=False)


def github_write_file(
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: Optional[str] = None
) -> Dict[str, Any]:
    """Create or update a file in GitHub repo using Contents API."""
    repo = normalize_repo(repo)
    branch = normalize_branch(branch)

    if not repo:
        raise ValueError("repo is required (owner/repo)")
    if not path or not path.strip():
        raise ValueError("path is required")
    if not message or not message.strip():
        raise ValueError("message is required")

    url = gh_contents_url(repo, path)
    # First: check if file exists to get sha
    sha = None
    r0 = gh_get(url, params={"ref": branch} if branch else None)
    if r0.status_code == 200:
        j0 = r0.json()
        if isinstance(j0, dict) and j0.get("sha"):
            sha = j0["sha"]
    elif r0.status_code in (404,):
        sha = None
    else:
        raise RuntimeError(f"GitHub preflight failed: {r0.status_code} {r0.text}")

    payload: Dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if branch:
        payload["branch"] = branch
    if sha:
        payload["sha"] = sha

    r1 = gh_put(url, payload)
    if r1.status_code not in (200, 201):
        raise RuntimeError(f"GitHub write failed: {r1.status_code} {r1.text}")

    return r1.json()


# ---------------------------
# Tool registry (used by /tools and MCP tools/list)
# ---------------------------
TOOLS = [
    {
        "name": "github_read_file",
        "description": "Read a file from a GitHub repo (returns raw text).",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "repo": {"type": "string", "description": "owner/repo (optional if DEFAULT_REPO is set)"},
                "path": {"type": "string", "description": "Path in repo, e.g. README.md"},
                "ref":  {"type": "string", "description": "Branch/tag/sha (optional)"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "github_write_file",
        "description": "Create or update a file in a GitHub repo and commit it.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "repo": {"type": "string", "description": "owner/repo (optional if DEFAULT_REPO is set)"},
                "path": {"type": "string", "description": "Path in repo, e.g. agent_outbox/bridge_test.txt"},
                "content": {"type": "string", "description": "File content (utf-8)"},
                "message": {"type": "string", "description": "Commit message"},
                "branch": {"type": "string", "description": "Branch (optional, default DEFAULT_BRANCH)"}
            },
            "required": ["path", "content", "message"]
        }
    },
    {
        "name": "health_check",
        "description": "Simple health check.",
        "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}, "required": []}
    }
]


def run_tool(name: str, args: Dict[str, Any]) -> str:
    """Return text result (MCP will wrap it)."""
    token_err = require_token()
    if name in ("github_read_file", "github_write_file") and token_err:
        # Raise to unify error handling downstream
        raise RuntimeError("Missing GITHUB_TOKEN on server")

    if name == "health_check":
        return json.dumps({
            "ok": True,
            "service": "ida-mcp-gateway",
            "version": APP_VERSION,
            "ts": now_iso(),
            "tools_loaded": len(TOOLS)
        }, ensure_ascii=False)

    if name == "github_read_file":
        repo = args.get("repo")
        path = args.get("path")
        ref = args.get("ref")
        if not path:
            raise ValueError("path is required")
        txt = github_read_file(repo=repo, path=path, ref=ref)
        return txt

    if name == "github_write_file":
        repo = args.get("repo")
        path = args.get("path")
        content = args.get("content")
        message = args.get("message")
        branch = args.get("branch")
        if not path or content is None or not message:
            raise ValueError("path, content, message are required")
        res = github_write_file(repo=repo, path=path, content=content, message=message, branch=branch)
        # keep response compact
        out = {
            "ok": True,
            "repo": normalize_repo(repo),
            "path": path,
            "branch": normalize_branch(branch),
            "commit": (res.get("commit") or {}).get("sha"),
            "content_sha": (res.get("content") or {}).get("sha"),
            "ts": now_iso()
        }
        return json.dumps(out, ensure_ascii=False)

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------
# Public endpoints
# ---------------------------
@app.get("/")
def index():
    # Always returns quickly; used by Render + your browser
    return jsonify({
        "message": "IDA MCP Gateway alive ✅",
        "service": "ida-mcp-gateway",
        "version": APP_VERSION,
        "tools_loaded": len(TOOLS),
        "ts": now_iso()
    })


@app.get("/tools")
def tools():
    # Agent Builder sometimes probes this; browser-friendly
    return jsonify(TOOLS)


# ---------------------------
# MCP JSON-RPC endpoint (THIS is what Agent Builder wants)
# ---------------------------
@app.post("/mcp")
def mcp():
    # MCP over JSON-RPC 2.0 (minimal)
    payload = request.get_json(silent=True) or {}
    rpc_id = payload.get("id", None)
    method = payload.get("method", "")
    params = payload.get("params", {}) or {}

    def ok(result: Any):
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": result})

    def err(code: int, message: str, data: Any = None):
        e = {"code": code, "message": message}
        if data is not None:
            e["data"] = data
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "error": e})

    try:
        # initialize
        if method == "initialize":
            # Keep it permissive; Agent Builder mostly wants a sane response.
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "ida-mcp-gateway", "version": APP_VERSION},
                "capabilities": {"tools": {}}
            }
            return ok(result)

        # tools/list
        if method == "tools/list":
            return ok({"tools": TOOLS})

        # tools/call
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {}) or {}
            if not name:
                return err(-32602, "Missing params.name")

            text = run_tool(name, arguments)

            # MCP "content" format
            return ok({
                "content": [
                    {"type": "text", "text": text}
                ]
            })

        # ping (optional)
        if method == "ping":
            return ok({"ok": True, "ts": now_iso()})

        return err(-32601, f"Method not found: {method}")

    except ValueError as ve:
        return err(-32602, "Invalid params", str(ve))
    except Exception as ex:
        return err(-32000, "Server error", str(ex))


# ---------------------------
# Render entry
# ---------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
