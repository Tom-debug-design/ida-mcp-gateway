import os
import requests
import base64

TOOL_NAME = "github_write_file"

TOOL_SPEC = {
    "name": "github_write_file",
    "description": "Create or update a file in a GitHub repo and commit it",
    "inputSchema": {
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "owner/repo"},
            "path": {"type": "string", "description": "file path in repo"},
            "content": {"type": "string", "description": "file content (plain text)"},
            "message": {"type": "string", "description": "commit message"},
            "branch": {"type": "string", "description": "branch name", "default": "main"}
        },
        "required": ["repo", "path", "content", "message"],
        "additionalProperties": False
    }
}

def run(args: dict) -> dict:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("IDA_MASTER_GITHUB")
    if not token:
        return {"ok": False, "error": "Missing GitHub token"}

    owner, repo = args["repo"].split("/", 1)
    path = args["path"]
    branch = args.get("branch", "main")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ida-mcp-gateway"
    }

    # Check if file exists to get SHA
    get_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    r = requests.get(get_url, headers=headers, timeout=20)
    sha = r.json().get("sha") if r.status_code == 200 else None

    put_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    payload = {
        "message": args["message"],
        "content": base64.b64encode(args["content"].encode()).decode(),
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    pr = requests.put(put_url, headers=headers, json=payload, timeout=20)
    if pr.status_code not in (200, 201):
        return {"ok": False, "status": pr.status_code, "body": pr.text[:500]}

    data = pr.json()
    return {
        "ok": True,
        "commit_sha": data.get("commit", {}).get("sha"),
        "url": data.get("content", {}).get("html_url")
    }
