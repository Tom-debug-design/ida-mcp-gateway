import os
import base64
import json
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ---------- Config ----------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
DEFAULT_REPO = os.getenv("DEFAULT_REPO", "").strip()  # e.g. "Tom-debug-design/atomicbot-agent"
DEFAULT_BRANCH = os.getenv("DEFAULT_BRANCH", "main").strip()
SERVICE_NAME = os.getenv("SERVICE_NAME", "ida-mcp-gateway").strip()
VERSION = os.getenv("VERSION", "1.4.0").strip()

GITHUB_API = "https://api.github.com"


def utc_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def require_env():
    if not GITHUB_TOKEN:
        return "Missing GITHUB_TOKEN env var"
    return None


def gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ida-mcp-gateway",
    }


def get_repo(payload):
    repo = (payload or {}).get("repo") or DEFAULT_REPO
    return (repo or "").strip()


def get_ref(payload):
    ref = (payload or {}).get("ref") or DEFAULT_BRANCH
    return (ref or "").strip()


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"text": (resp.text or "")[:2000]}


# ---------- Tool implementations ----------
def tool_health_check(_payload):
    return {
        "ok": True,
        "message": "IDA MCP Gateway alive ✅",
        "service": SERVICE_NAME,
        "version": VERSION,
        "ts": utc_iso(),
        "defaults": {"repo": DEFAULT_REPO or None, "ref": DEFAULT_BRANCH},
    }


def tool_github_read_file(payload):
    err = require_env()
    if err:
        return {"ok": False, "error": err}

    path = (payload or {}).get("path")
    if not path:
        return {"ok": False, "error": "Missing required input: path"}

    repo = get_repo(payload)
    if not repo:
        return {"ok": False, "error": "No repo provided and DEFAULT_REPO is not set"}

    ref = get_ref(payload)

    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    r = requests.get(url, headers=gh_headers(), params={"ref": ref}, timeout=30)

    if r.status_code != 200:
        return {"ok": False, "error": "GitHub read failed", "status": r.status_code, "details": safe_json(r)}

    data = r.json()
    content_b64 = (data.get("content") or "").encode("utf-8")
    try:
        decoded = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception:
        decoded = ""

    return {"ok": True, "repo": repo, "ref": ref, "path": path, "sha": data.get("sha"), "text": decoded}


def tool_github_write_file(payload):
    err = require_env()
    if err:
        return {"ok": False, "error": err}

    path = (payload or {}).get("path")
    content = (payload or {}).get("content")
    message = (payload or {}).get("message") or (f"Update {path}" if path else "Update file")

    if not path:
        return {"ok": False, "error": "Missing required input: path"}
    if content is None:
        return {"ok": False, "error": "Missing required input: content"}

    repo = get_repo(payload)
    if not repo:
        return {"ok": False, "error": "No repo provided and DEFAULT_REPO is not set"}

    ref = get_ref(payload)

    # Get existing SHA if file exists
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
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


# ---------- MCP tool schema (what Builder needs) ----------
MCP_TOOLS = [
    {
        "name": "health_check",
        "description": "Simple health check.",
        "inputSchema": {"type": "object", "additionalProperties": True, "properties": {}},
    },
    {
        "name": "github_read_file",
        "description": "Read a file from a GitHub repo (returns raw text). If repo/ref omitted, server uses DEFAULT_REPO/DEFAULT_BRANCH.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "path": {"type": "string"},
                "repo": {"type": "string"},
                "ref": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "github_write_file",
        "description": "Create or update a file in a GitHub repo and commit it. If repo/ref omitted, server uses DEFAULT_REPO/DEFAULT_BRANCH.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "message": {"type": "string"},
                "repo": {"type": "string"},
                "ref": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
]


def run_tool(name, args):
    if name == "health_check":
        return tool_health_check(args)
    if name == "github_read_file":
        return tool_github_read_file(args)
    if name == "github_write_file":
        return tool_github_write_file(args)
    return {"ok": False, "error": f"Unknown tool: {name}"}


# ---------- Basic endpoints ----------
@app.get("/")
def root():
    return jsonify(tool_health_check({}))


@app.get("/health")
def health():
    return jsonify(tool_health_check({}))


# Keep these for manual testing (nice-to-have)
@app.get("/tools")
def tools():
    return jsonify(MCP_TOOLS)


@app.post("/invoke")
def invoke():
    data = request.get_json(silent=True) or {}
    tool_name = data.get("tool") or data.get("name")
    payload = data.get("input") or data.get("arguments") or data.get("payload") or {}
    return jsonify(run_tool(tool_name, payload))


# ---------- THE FIX: MCP JSON-RPC endpoint ----------
@app.route("/mcp", methods=["GET", "POST"])
def mcp():
    # Some clients probe with GET
    if request.method == "GET":
        return jsonify({"ok": True, "service": SERVICE_NAME, "version": VERSION})

    msg = request.get_json(silent=True) or {}
    rpc_id = msg.get("id", None)
    method = msg.get("method") or ""

    # Minimal MCP-ish JSON-RPC surface
    if method in ("tools/list", "mcp.tools.list"):
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": MCP_TOOLS}})

    if method in ("tools/call", "mcp.tools.call"):
        params = msg.get("params") or {}
        name = params.get("name") or params.get("tool") or ""
        args = params.get("arguments") or params.get("input") or {}
        result = run_tool(name, args)
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": result})

    # Optional init/ping style calls
    if method in ("initialize", "ping"):
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": {"ok": True}})

    return jsonify({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
