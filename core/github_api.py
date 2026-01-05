from __future__ import annotations
import base64
import json
import requests
from typing import Optional, Dict, Any


class GitHubAPI:
    def __init__(self, token: str) -> None:
        if not token or token.strip() == "":
            raise RuntimeError("GH_PAT mangler (token er tom).")
        self.token = token.strip()
        self.base = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "ida-mcp-gateway",
        }

    def _req(self, method: str, url: str, **kwargs) -> requests.Response:
        r = requests.request(method, url, headers=self.headers, timeout=60, **kwargs)
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub API {r.status_code}: {r.text}")
        return r

    def get_file_sha(self, repo: str, path: str, branch: str = "main") -> Optional[str]:
        url = f"{self.base}/repos/{repo}/contents/{path}"
        r = requests.get(url, headers=self.headers, params={"ref": branch}, timeout=60)
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub get_file_sha {r.status_code}: {r.text}")
        data = r.json()
        return data.get("sha")

    def put_file(
        self,
        repo: str,
        path: str,
        content_text: str,
        message: str,
        branch: str = "main",
    ) -> Dict[str, Any]:
        url = f"{self.base}/repos/{repo}/contents/{path}"

        sha = self.get_file_sha(repo, path, branch=branch)
        content_b64 = base64.b64encode(content_text.encode("utf-8")).decode("utf-8")

        payload: Dict[str, Any] = {
            "message": message,
            "content": content_b64,
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        r = self._req("PUT", url, json=payload)
        return r.json()
