import os
import base64
import json
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS

app = Flask(__name__)

# CORS: Builder er en diva. Gi den alt den trenger.
CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=False,
)

# ---------- Config ----------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
DEFAULT_REPO = os.getenv("DEFAULT_REPO", "").strip()  # e.g. "Tom-debug-design/atomicbot-agent"
DEFAULT_BRANCH = os.getenv("DEFAULT_BRANCH", "main").strip()
SERVICE_NAME = os.getenv("SERVICE_NAME", "ida-mcp-gateway").strip()
VERSION = os.getenv("VERSION", "1.4.1").strip()

GITHUB_API = "https://api.github.com"


def utc_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def require_env():
    if not GITHUB_TOKEN:
        return "Missing GITHUB_TOKEN env var"
    if not DEFAULT_REPO:
        return "Missing DEFAULT_REPO env var (owner/repo)"
    return None


def gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ida-mcp-gateway",
    }


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"text": (resp.text or "")[:2000]}


# Hard “no-cache” to stop builder from caching bad tool lists
@app.after_request
def add_common_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ---------- Tool implementations ----------
def tool_health_check(_payload):
    return {
        "ok": True,
        "message": "IDA MCP Gateway alive ✅",
        "service": SERVICE_NAME,
        "version": VERSION,
        "ts": utc_iso(),
        "defaults": {
            "repo": DEFAULT_REPO or None,
            "ref": DEFAULT_BRANCH,
        },
        "tools_loaded": 3,
    }


def tool_github_read_file(payload):
    err = require_env()
    if err:
        return {"ok": False, "error": err}

    path = (payload or {}).get("path")
    if not path:
        return {"ok": False, "error": "Missing required input: path"}

    repo = DEFAULT_REPO
    ref = DEFAULT_BRANCH

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
    content_b64 = (data.get("content") or "").replace("\n", "")
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


def tool_github_write_file(payload):
    err = require_env()
    if err:
        return {"ok": False, "error": err}

    path = (payload or {}).get("path")
    content = (payload or {}).get("content")
    message = (payload or {}).get("message") or f"Update {path or 'file'}"

    if not path:
        return {"ok": False, "error": "Missing required input: path"}
    if content is None:
        return {"ok": False, "error": "Missing required input: content"}

    repo = DEFAULT_REPO
    ref = DEFAULT_BRANCH

    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"

    # Check existing SHA (optional update)
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
        return {
            "ok": False,
            "error": "GitHub write failed",
            "status": put_r.status_code,
            "details": safe_json(put_r),
        }

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


# ---------- Endpoints ----------
@app.route("/", methods=["GET", "OPTIONS"])
def root():
    if request.method == "OPTIONS":
        return make_response("", 204)
    return jsonify(tool_health_check({}))


@app.route("/health", methods=["GET", "OPTIONS"])
def health():
    if request.method == "OPTIONS":
        return make_response("", 204)
    return jsonify(tool_health_check({}))


@app.route("/tools", methods=["GET", "OPTIONS"])
def tools():
    if request.method == "OPTIONS":
        return make_response("", 204)

    # IMPORTANT: Minimal schemas to avoid builder “triangle”.
    # Do NOT expose repo/ref as fields. Use DEFAULT_REPO/DEFAULT_BRANCH server-side.
    tool_list = [
        {
            "name": "health_check",
            "description": "Simple health check.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": True,
                "properties": {},
            },
        },
        {
            "name": "github_read_file",
            "description": "Read a file from DEFAULT_REPO (server-side) and return raw text.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "path": {"type": "string", "description": "Path in repo, e.g. README.md"},
                },
                "required": ["path"],
            },
        },
        {
            "name": "github_write_file",
            "description": "Create/update a file in DEFAULT_REPO (server-side) and commit it.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "path": {"type": "string", "description": "Path in repo, e.g. agent_outbox/bridge_test.txt"},
                    "content": {"type": "string", "description": "File content (utf-8 string)"},
                    "message": {"type": "string", "description": "Commit message (optional)"},
                },
                "required": ["path", "content"],
            },
        },
    ]

    # Return as object (some clients prefer this over raw list)
    return jsonify(
        {
            "service": SERVICE_NAME,
            "version": VERSION,
            "ts": utc_iso(),
            "tools": tool_list,
        }
    )


@app.route("/invoke", methods=["POST", "OPTIONS"])
def invoke():
    if request.method == "OPTIONS":
        return make_response("", 204)

    data = request.get_json(silent=True) or {}

    tool_name = data.get("tool") or data.get("name")
    payload = data.get("input") or data.get("arguments") or data.get("payload") or {}

    if tool_name == "health_check":
        return jsonify(tool_health_check(payload))

    if tool_name == "github_read_file":
        return jsonify(tool_github_read_file(payload))

    if tool_name == "github_write_file":
        return jsonify(tool_github_write_file(payload))

    return jsonify({"ok": False, "error": f"Unknown tool: {tool_name}"}), 400


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
