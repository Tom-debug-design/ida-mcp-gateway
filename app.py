import os
import base64
import json
from datetime import datetime

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

SERVICE_NAME = "ida-mcp-gateway"
VERSION = "1.4.0"

# ---- GitHub config ----
GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("AGENT_TOKEN")

DEFAULT_REPO = os.getenv("DEFAULT_REPO", "").strip()  # optional: "owner/repo"
DEFAULT_BRANCH = os.getenv("DEFAULT_BRANCH", "main").strip()


# -----------------------------
# MCP-ish tool registry
# -----------------------------
TOOLS = [
    {
        "name": "github_read_file",
        "description": "Read a file from a GitHub repo (returns raw text).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "owner/repo (optional if DEFAULT_REPO set)"},
                "path": {"type": "string", "description": "path in repo, e.g. README.md"},
                "ref": {"type": "string", "description": "branch/tag/sha (optional, defaults to DEFAULT_BRANCH)"}
            },
            # IMPORTANT: keep required empty -> avoids builder red triangle
            "required": [],
            "additionalProperties": False
        }
    },
    {
        "name": "github_write_file",
        "description": "Create or update a file in a GitHub repo and commit it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "owner/repo (optional if DEFAULT_REPO set)"},
                "path": {"type": "string", "description": "path in repo, e.g. agent_outbox/bridge_test.txt"},
                "content": {"type": "string", "description": "file content (utf-8 string)"},
                "message": {"type": "string", "description": "commit message"},
                "branch": {"type": "string", "description": "branch (optional, defaults to DEFAULT_BRANCH)"}
            },
            # IMPORTANT: keep required empty -> avoids builder red triangle
            "required": [],
            "additionalProperties": False
        }
    },
    {
        "name": "health_check",
        "description": "Simple health check.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        }
    }
]


# -----------------------------
# Helpers
# -----------------------------
def _gh_headers():
    if not GITHUB_TOKEN:
        # No token -> we still expose tools, but calls will return a clear error
        return {"Accept": "application/vnd.github+json"}
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }


def _resolve_repo(repo: str | None) -> str:
    repo = (repo or "").strip()
    if repo:
        return repo
    if DEFAULT_REPO:
        return DEFAULT_REPO
    raise ValueError("Missing 'repo'. Set DEFAULT_REPO env or pass repo='owner/repo'.")


def _resolve_ref(ref: str | None) -> str:
    ref = (ref or "").strip()
    return ref if ref else DEFAULT_BRANCH


def _require_token():
    if not GITHUB_TOKEN:
        raise ValueError("Missing GitHub token. Set env GITHUB_TOKEN (or GH_TOKEN/AGENT_TOKEN).")


# -----------------------------
# Tool implementations
# -----------------------------
def tool_health_check(_args: dict):
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "version": VERSION,
        "time": datetime.utcnow().isoformat() + "Z",
        "tools_loaded": len(TOOLS)
    }


def tool_github_read_file(args: dict):
    _require_token()
    repo = _resolve_repo(args.get("repo"))
    path = (args.get("path") or "").strip()
    ref = _resolve_ref(args.get("ref"))

    if not path:
        raise ValueError("Missing 'path' (e.g. README.md).")

    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    r = requests.get(url, headers=_gh_headers(), params={"ref": ref}, timeout=30)
    if r.status_code >= 400:
        raise ValueError(f"GitHub read failed ({r.status_code}): {r.text}")

    data = r.json()
    if isinstance(data, dict) and data.get("type") == "file":
        content_b64 = data.get("content", "")
        decoded = base64.b64decode(content_b64).decode("utf-8", errors="replace")
        return {
            "repo": repo,
            "path": path,
            "ref": ref,
            "sha": data.get("sha"),
            "text": decoded
        }

    # If it’s a directory or other type
    return {
        "repo": repo,
        "path": path,
        "ref": ref,
        "data": data
    }


def tool_github_write_file(args: dict):
    _require_token()
    repo = _resolve_repo(args.get("repo"))
    path = (args.get("path") or "").strip()
    content = args.get("content", "")
    message = (args.get("message") or "").strip()
    branch = _resolve_ref(args.get("branch"))

    if not path:
        raise ValueError("Missing 'path' (e.g. agent_outbox/bridge_test.txt).")
    if not message:
        raise ValueError("Missing 'message' (commit message).")

    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"

    # Check if file exists -> get sha
    sha = None
    get_r = requests.get(url, headers=_gh_headers(), params={"ref": branch}, timeout=30)
    if get_r.status_code == 200:
        sha = get_r.json().get("sha")

    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    put_r = requests.put(url, headers=_gh_headers(), json=payload, timeout=30)
    if put_r.status_code >= 400:
        raise ValueError(f"GitHub write failed ({put_r.status_code}): {put_r.text}")

    out = put_r.json()
    return {
        "repo": repo,
        "path": path,
        "branch": branch,
        "commit_sha": (out.get("commit") or {}).get("sha"),
        "content_sha": (out.get("content") or {}).get("sha"),
        "url": (out.get("content") or {}).get("html_url")
    }


TOOL_FUNCS = {
    "health_check": tool_health_check,
    "github_read_file": tool_github_read_file,
    "github_write_file": tool_github_write_file,
}


# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def root():
    return jsonify({
        "message": f"IDA MCP Gateway alive ✅",
        "service": SERVICE_NAME,
        "version": VERSION,
        "tools_loaded": len(TOOLS)
    })


# Tool discovery (builder needs this)
@app.get("/tools")
@app.get("/mcp/tools")
def list_tools():
    return jsonify({"tools": TOOLS})


# Tool execution (simple JSON contract)
# Expected input: {"name":"github_write_file","arguments":{...}}
@app.post("/call")
@app.post("/mcp/call")
def call_tool():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "").strip()
    args = body.get("arguments") or {}

    if name not in TOOL_FUNCS:
        return jsonify({"ok": False, "error": f"Unknown tool: {name}"}), 400

    try:
        result = TOOL_FUNCS[name](args)
        return jsonify({"ok": True, "tool": name, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "tool": name, "error": str(e)}), 400


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)
