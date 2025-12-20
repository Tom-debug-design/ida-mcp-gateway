from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import requests

app = Flask(__name__)
CORS(app)

SERVICE_NAME = "ida-mcp-gateway"
VERSION = "1.3.1"

DEFAULT_REPO = os.getenv("DEFAULT_REPO", "")
DEFAULT_BRANCH = os.getenv("DEFAULT_BRANCH", "main")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

def _json_no_cache(payload, status=200):
    resp = jsonify(payload)
    resp.status_code = status
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp

@app.route("/", methods=["GET"])
def health():
    return _json_no_cache({
        "message": "IDA MCP Gateway alive ✅",
        "service": SERVICE_NAME,
        "version": VERSION
    })

def tools_payload():
    # Minimal, strict MCP-ish tool schema Builder tåler
    return {
        "tools": [
            {
                "name": "github_read_file",
                "description": "Read a file from a GitHub repo (returns raw text).",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "repo": {"type": "string", "description": "owner/repo (optional if DEFAULT_REPO set)"},
                        "path": {"type": "string", "description": "path in repo, e.g. README.md"},
                        "ref": {"type": "string", "description": "branch/tag/sha (optional, defaults to DEFAULT_BRANCH)"}
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
                        "repo": {"type": "string", "description": "owner/repo (optional if DEFAULT_REPO set)"},
                        "path": {"type": "string", "description": "path in repo, e.g. agent_outbox/bridge_test.txt"},
                        "content": {"type": "string", "description": "file content (utf-8 string)"},
                        "message": {"type": "string", "description": "commit message"},
                        "branch": {"type": "string", "description": "branch (optional, defaults to DEFAULT_BRANCH)"}
                    },
                    "required": ["path", "content", "message"]
                }
            }
        ]
    }

@app.route("/tools", methods=["GET"])
def tools():
    return _json_no_cache(tools_payload())

# Builder-safe discovery route
@app.route("/.well-known/mcp/tools", methods=["GET"])
def tools_well_known():
    return _json_no_cache(tools_payload())

def gh_headers():
    if not GITHUB_TOKEN:
        return None
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ida-mcp-gateway"
    }

@app.route("/call/github_read_file", methods=["POST"])
def call_github_read_file():
    data = request.get_json(force=True, silent=True) or {}
    repo = data.get("repo") or DEFAULT_REPO
    path = data.get("path")
    ref = data.get("ref") or DEFAULT_BRANCH

    if not repo or not path:
        return _json_no_cache({"error": "Missing repo or path"}, 400)

    headers = gh_headers()
    if not headers:
        return _json_no_cache({"error": "GITHUB_TOKEN not set"}, 500)

    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    r = requests.get(url, headers=headers, params={"ref": ref})
    if r.status_code != 200:
        return _json_no_cache({"error": "GitHub read failed", "status": r.status_code, "body": r.text}, 500)

    js = r.json()
    import base64
    content_b64 = js.get("content", "")
    decoded = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    return _json_no_cache({"text": decoded})

@app.route("/call/github_write_file", methods=["POST"])
def call_github_write_file():
    data = request.get_json(force=True, silent=True) or {}
    repo = data.get("repo") or DEFAULT_REPO
    path = data.get("path")
    content = data.get("content")
    message = data.get("message")
    branch = data.get("branch") or DEFAULT_BRANCH

    if not repo or not path or content is None or not message:
        return _json_no_cache({"error": "Missing repo/path/content/message"}, 400)

    headers = gh_headers()
    if not headers:
        return _json_no_cache({"error": "GITHUB_TOKEN not set"}, 500)

    import base64
    url = f"https://api.github.com/repos/{repo}/contents/{path}"

    # check existing SHA
    sha = None
    r0 = requests.get(url, headers=headers, params={"ref": branch})
    if r0.status_code == 200:
        sha = r0.json().get("sha")

    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload)
    if r.status_code not in (200, 201):
        return _json_no_cache({"error": "GitHub write failed", "status": r.status_code, "body": r.text}, 500)

    return _json_no_cache({"ok": True, "repo": repo, "path": path, "branch": branch})
