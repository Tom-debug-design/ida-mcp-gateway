#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

def die(msg: str, code: int = 0) -> None:
    print(msg)
    sys.exit(code)

def main() -> None:
    if len(sys.argv) != 2:
        die("Usage: outbox_runner.py <path-to-outbox-json>", 0)

    job_path = Path(sys.argv[1])

    if not job_path.exists():
        die(f"Outbox file not found: {job_path}", 0)

    # Read JSON safely
    try:
        raw = job_path.read_text(encoding="utf-8").strip()
        if not raw:
            die(f"Outbox file is empty: {job_path}", 0)
        data = json.loads(raw)
    except Exception as e:
        die(f"JSON parse failed for {job_path}: {e}", 0)

    action = str(data.get("action", "")).strip()
    print(f"Action: {action}")

    if action != "write_result":
        die("Not write_result -> exit.", 0)

    out_path = str(data.get("out_path", "")).strip()
    out_content = data.get("out_content", "")

    # FORCE output into agent_results for easy control (as you requested)
    if not out_path:
        out_path = "agent_results/hello.txt"
    if not out_path.startswith("agent_results/"):
        out_path = "agent_results/" + out_path.lstrip("/")

    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # Ensure it's written within repo working dir
    # (GitHub Actions runs in repo root after checkout)
    out_file.write_text(str(out_content), encoding="utf-8")

    print(f"Wrote: {out_file}")

if __name__ == "__main__":
    main()
