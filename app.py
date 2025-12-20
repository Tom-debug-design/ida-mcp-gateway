from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import os
import time
import json
import base64
import requests

app = Flask(__name__)
CORS(app)

# ----------------------------
# Config
# ----------------------------
GITHUB_API = "https://api.github.com"
DEFAULT_BRANCH = os.getenv("GITHUB_BRANCH", "main")

def get_github_token() -> str | None:
    # Prioritet: GITHUB_TOKEN -> IDA_MASTER_GITHUB -> GITHUB_PAT
    return (
        os.getenv("GITHUB_TOKEN")
        or os.getenv("IDA_MASTER_GITHUB")
        or os.getenv("GITHUB_PAT")
    )

def gh_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ida-mcp-gateway",
    }

def err_result(message: str):
    return {
        "content": [{"type": "text", "text": f"❌ {message}"}]
    }

def ok_text(message: str):
    return {
        "content": [{"type": "text", "text": message}]
    }

# ----------------------------
# MCP Tool Registry (REAL tools)
# ----------------------------
TOOLS = [
    {
        "name": "github_read_file",
        "description": "Read a file from a GitHub repo (returns decoded text content when possible).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "owner/repo"},
                "path": {"type": "string", "description": "path in repo"},
                "ref": {"type": "string", "description": "branch/tag/sha (optional)"},
            },
            "required": ["repo", "path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "github_write_file",
        "description": "Create or update a file in a GitHub repo and commit it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "owner/repo"},
                "path": {"type": "string", "description": "path in repo"},
                "content": {"type": "string", "description": "raw text content to write"},
                "message": {"type": "string", "description": "commit message"},
                "branch": {"type": "string", "description": "branch (optional, default main)"},
            },
            "required": ["repo", "path", "content", "message"],
            "additionalProperties": False,
        },
    },
]

# ----------------------------
# Tool Implementations
# ----------------------------
def github_read_file(args: dict) -> dict:
    token = get_github_token()
    if not token:
        return err_result("Missing GitHub token env var. Set GITHUB_TOKEN (recommended) or IDA_MASTER_GITHUB.")

    repo = args.get("repo")
    path = args.get("path")
    ref = args.get("ref")

    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    params = {}
    if ref:
        params["ref"] = ref

    r = requests.get(url, headers=gh_headers(token), params=params, timeout=20)
    if r.status_code != 200:
        return err_result(f"GitHub read failed ({r.status_code}): {r.text}")

    data = r.json()
    # If it's a file, GitHub returns base64 content
    if data.get("type") != "file":
        return err_result("Path is not a file.")

    b64 = data.get("content", "")
    encoding = data.get("encoding")
    if encoding == "base64" and b64:
        try:
            raw = base64.b64decode(b64).decode("utf-8", errors="replace")
        except Exception:
            raw = base64.b64decode(b64).decode("latin-1", errors="replace")
        return ok_text(raw)

    return err_result("Could not decode content.")

def github_write_file(args: dict) -> dict:
    token = get_github_token()
    if not token:
        return err_result("Missing GitHub token env var. Set GITHUB_TOKEN (recommended) or IDA_MASTER_GITHUB.")

    repo = args.get("repo")
    path = args.get("path")
    content = args.get("content", "")
    message = args.get("message")
    branch = args.get("branch") or DEFAULT_BRANCH

    # 1) check if file exists -> get sha
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    params = {"ref": branch}
    sha = None

    r_get = requests.get(url, headers=gh_headers(token), params=params, timeout=20)
    if r_get.status_code == 200:
        sha = r_get.json().get("sha")
    elif r_get.status_code in (404,):
        sha = None
    else:
        return err_result(f"GitHub pre-check failed ({r_get.status_code}): {r_get.text}")

    # 2) PUT create/update
    b64_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {
        "message": message,
        "content": b64_content,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r_put = requests.put(url, headers=gh_headers(token), json=payload, timeout=20)
    if r_put.status_code not in (200, 201):
        return err_result(f"GitHub write failed ({r_put.status_code}): {r_put.text}")

    out = r_put.json()
    commit_sha = (out.get("commit") or {}).get("sha", "")
    html_url = ((out.get("content") or {}).get("html_url")) or ""

    return ok_text(
        "✅ GitHub write OK\n"
        f"- repo: {repo}\n"
        f"- path: {path}\n"
        f"- branch: {branch}\n"
        f"- commit: {commit_sha}\n"
        f"- url: {html_url}"
    )

def call_tool(name: str, arguments: dict) -> dict:
    if name == "github_read_file":
        return github_read_file(arguments)
    if name == "github_write_file":
        return github_write_file(arguments)
    return err_result(f"Unknown tool: {name}")

# ----------------------------
# Basic health
# ----------------------------
@app.get("/")
def root():
    return jsonify({
        "message": "IDA MCP Gateway alive ✅",
        "service": "ida-mcp-gateway",
        "tools_loaded": len(TOOLS),
        "version": "2.0.0"
    })

# ----------------------------
# MCP over HTTP (JSON-RPC)
# ----------------------------
@app.route("/mcp", methods=["GET", "POST"])
def mcp_http():
    # Common non-standard discovery
    if request.method == "GET":
        return jsonify({"tools": TOOLS})

    payload = request.get_json(silent=True) or {}
    method = payload.get("method")
    params = payload.get("params") or {}
    rpc_id = payload.get("id")

    # "initialize" handshake (some clients call this first)
    if method == "initialize":
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ida-mcp-gateway", "version": "2.0.0"},
            },
        })

    if method == "tools/list":
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"tools": TOOLS},
        })

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        result = call_tool(tool_name, arguments)
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": result,
        })

    return jsonify({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    })

# ----------------------------
# MCP over SSE (optional, for clients that require streaming)
# ----------------------------
@app.get("/mcp/sse")
def mcp_sse():
    def stream():
        yield 'event: ready\ndata: {"status":"ok"}\n\n'
        while True:
            yield f'event: ping\ndata: {{"t":{int(time.time())}}}\n\n'
            time.sleep(15)

    return Response(stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
