import os
import base64
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ---------- Config ----------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
DEFAULT_REPO = os.getenv("DEFAULT_REPO", "").strip()      # optional
DEFAULT_BRANCH = os.getenv("DEFAULT_BRANCH", "main").strip()
SERVICE_NAME = os.getenv("SERVICE_NAME", "ida-mcp-gateway").strip()
VERSION = os.getenv("VERSION", "1.4.1").strip()

GITHUB_API = "https://api.github.com"


def utc_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ida-mcp-gateway",
    }


def ok_json(payload, status=200):
    resp = make_response(jsonify(payload), status)
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    return resp


# ---------- Tool logic ----------
def tool_health_check(_payload=None):
    return {
        "ok": True,
        "message": "IDA MCP Gateway alive ✅",
        "service": SERVICE_NAME,
        "version": VERSION,
        "ts": utc_iso(),
        "defaults": {"repo": DEFAULT_REPO or None, "ref": DEFAULT_BRANCH},
    }


def tool_github_read_file(payload):
    if not GITHUB_TOKEN:
        return {"ok": False, "error": "Missing GITHUB_TOKEN env var"}

    payload = payload or {}

    # NOTE: We intentionally allow missing fields (schema has no required)
    path = (payload.get("path") or "").strip()
    repo = (payload.get("repo") or DEFAULT_REPO or "").strip()
    ref = (payload.get("ref") or DEFAULT_BRANCH or "").strip()

    if not path:
        return {"ok": False, "error": "Missing input: path"}
    if not repo:
        return {"ok": False, "error": "Missing input: repo (and DEFAULT_REPO not set)"}

    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    r = requests.get(url, headers=gh_headers(), params={"ref": ref}, timeout=30)

    if r.status_code != 200:
        try:
            details = r.json()
        except Exception:
            details = {"text": r.text[:2000]}
        return {"ok": False, "error": "GitHub read failed", "status": r.status_code, "details": details}

    data = r.json()
    content_b64 = (data.get("content") or "").encode("utf-8")
    try:
        decoded = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception:
        decoded = ""

    return {"ok": True, "repo": repo, "ref": ref, "path": path, "sha": data.get("sha"), "text": decoded}


# ---------- Routes ----------
@app.get("/")
def root():
    return ok_json(tool_health_check({}))


@app.get("/health")
def health():
    return ok_json(tool_health_check({}))


@app.get("/tools")
def tools():
    # CRITICAL: no required fields here. Builder edge validation must not demand inputs.
    tools_list = [
        {
            "name": "health_check",
            "description": "Simple health check.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "github_read_file",
            "description": "Read a file from GitHub and return raw text. (Inputs are OPTIONAL in schema; server will error if path missing.)",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string", "description": "Path in repo, e.g. README.md"},
                    "repo": {"type": "string", "description": "owner/repo (optional, defaults to DEFAULT_REPO)"},
                    "ref": {"type": "string", "description": "branch/tag/sha (optional, defaults to DEFAULT_BRANCH)"},
                },
                "required": [],
            },
            "input_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string", "description": "Path in repo, e.g. README.md"},
                    "repo": {"type": "string", "description": "owner/repo (optional, defaults to DEFAULT_REPO)"},
                    "ref": {"type": "string", "description": "branch/tag/sha (optional, defaults to DEFAULT_BRANCH)"},
                },
                "required": [],
            },
        },
    ]
    # Some builders expect {"tools":[...]} instead of a raw list
    return ok_json({"tools": tools_list})


@app.route("/invoke", methods=["POST", "OPTIONS"])
def invoke():
    if request.method == "OPTIONS":
        return ok_json({"ok": True})

    data = request.get_json(silent=True) or {}

    # Accept multiple variants
    tool_name = data.get("tool") or data.get("name") or data.get("tool_name")
    payload = data.get("input") or data.get("arguments") or data.get("payload") or {}

    if tool_name == "health_check":
        return ok_json(tool_health_check(payload))
    if tool_name == "github_read_file":
        return ok_json(tool_github_read_file(payload))

    return ok_json({"ok": False, "error": f"Unknown tool: {tool_name}"}, status=400)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
