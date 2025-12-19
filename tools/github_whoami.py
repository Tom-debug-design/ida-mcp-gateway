import os
import requests

TOOL_NAME = "github_whoami"

TOOL_SPEC = {
    "name": "github_whoami",
    "description": "Verify GitHub token works by returning the authenticated user login.",
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
}

def run(args: dict) -> dict:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("IDA_MASTER_GITHUB") or os.getenv("GITHUB_PAT")
    if not token:
        return {
            "ok": False,
            "error": "Missing GitHub token env var. Set GITHUB_TOKEN (recommended) or IDA_MASTER_GITHUB."
        }

    r = requests.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "ida-mcp-gateway",
        },
        timeout=15,
    )

    if r.status_code != 200:
        return {"ok": False, "status": r.status_code, "body": r.text[:500]}

    data = r.json()
    return {"ok": True, "login": data.get("login"), "id": data.get("id")}
