#!/usr/bin/env python3
import json
import sys
from pathlib import Path

def die(msg: str, code: int = 1):
    print(msg)
    sys.exit(code)

def main():
    if len(sys.argv) != 2:
        die("Usage: outbox_runner.py <job.json>")

    job_path = Path(sys.argv[1])

    if not job_path.exists():
        die(f"Outbox file not found: {job_path}")

    try:
        data = json.loads(job_path.read_text(encoding="utf-8"))
    except Exception as e:
        die(f"JSON parse failed: {e}")

    action = data.get("action")

    if action != "write_result":
        die(f"Unsupported action: {action}")

    out_path = data.get("out_path", "agent_results/hello.txt")
    out_content = data.get("out_content", "")

    if not out_path.startswith("agent_results/"):
        out_path = "agent_results/" + out_path.lstrip("/")

    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(str(out_content), encoding="utf-8")

    print(f"Wrote: {out_file}")

if __name__ == "__main__":
    main()
