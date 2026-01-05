from __future__ import annotations
import os
import json
from datetime import datetime, timezone
from typing import Dict, List

from core.github_api import GitHubAPI

STATE_FILE = ".ida_publish_state.json"


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_state() -> Dict[str, str]:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: Dict[str, str]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def list_files_recursive(root: str) -> List[str]:
    out: List[str] = []
    if not os.path.isdir(root):
        return out
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.startswith("."):
                continue
            full = os.path.join(dirpath, fn)
            out.append(full)
    out.sort()
    return out


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main() -> None:
    token = os.getenv("GH_PAT", "").strip()
    repos = os.getenv("TARGET_REPOS", "").strip()
    if not repos:
        raise RuntimeError("TARGET_REPOS mangler. Eks: owner/repoA,owner/repoB")

    gh = GitHubAPI(token)
    targets = [r.strip() for r in repos.split(",") if r.strip()]

    state = load_state()

    # Samle filer vi vil publisere
    publish_roots = ["agent_results", "ops/logs"]
    all_files: List[str] = []
    for root in publish_roots:
        all_files += list_files_recursive(root)

    if not all_files:
        print("No files to publish.")
        return

    # Publiser kun de som er nye/endrede siden sist (basert på mtime)
    published_any = False
    for fpath in all_files:
        mtime = str(os.path.getmtime(fpath))
        if state.get(fpath) == mtime:
            continue

        content = read_text(fpath)
        rel = fpath.replace("\\", "/")  # windows-safe

        for repo in targets:
            # Vi speiler samme path i target repo.
            # Eks: agent_results/job_xxx_output.md -> agent_results/job_xxx_output.md
            msg = f"IDA publish: {rel}"
            resp = gh.put_file(
                repo=repo,
                path=rel,
                content_text=content,
                message=msg,
                branch="main",
            )
            sha = resp.get("commit", {}).get("sha")
            html = resp.get("content", {}).get("html_url")
            print(f"PUBLISHED -> {repo} :: {rel} :: sha={sha} :: url={html}")

        state[fpath] = mtime
        published_any = True

    save_state(state)

    if not published_any:
        print("Nothing new to publish (state unchanged).")
    else:
        print(f"Publish done. Updated {STATE_FILE}.")


if __name__ == "__main__":
    main()
