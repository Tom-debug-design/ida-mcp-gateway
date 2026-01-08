# worker/task_router.py
from __future__ import annotations

import os
import json
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from worker.tasks.roi_scan import run_roi_scan


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_text(path: str, text: str) -> None:
    _ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _write_json(path: str, data: Any) -> None:
    _ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _append_log(path: str, line: str) -> None:
    _ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def _move(src: str, dst: str) -> None:
    _ensure_dir(os.path.dirname(dst))
    shutil.move(src, dst)


def _job_type(job: Dict[str, Any], filename: str) -> str:
    jt = (job.get("job_type") or job.get("type") or job.get("job") or "").strip()
    if jt:
        return jt
    # fallback: derive from filename like 001_roi_scan.json
    base = os.path.basename(filename).lower()
    if "roi_scan" in base:
        return "ROI_SCAN"
    return "UNKNOWN"


def _list_jobs(outbox_dir: str) -> List[str]:
    if not os.path.isdir(outbox_dir):
        return []
    files = []
    for name in os.listdir(outbox_dir):
        if name.lower().endswith(".json"):
            files.append(os.path.join(outbox_dir, name))
    files.sort()
    return files


def _result_paths(results_dir: str) -> Tuple[str, str]:
    # main stable result file + timestamped result
    main = os.path.join(results_dir, "ROI_PLAN.md")
    stamped = os.path.join(results_dir, f"ROI_PLAN.{_utc_stamp()}.md")
    return main, stamped


def process_one(job_path: str, outbox_done: str, results_dir: str, needs_dir: str, autorun_log_path: str) -> None:
    name = os.path.basename(job_path)
    try:
        job = _read_json(job_path)
    except Exception as e:
        # If job is corrupt, move it aside as FAILED
        failed_name = f"{os.path.splitext(name)[0]}.FAILED.{_utc_stamp()}.json"
        _move(job_path, os.path.join(outbox_done, failed_name))
        _append_log(autorun_log_path, f"[{_utc_iso()}] ROI_SCAN read failed for {name}: {type(e).__name__}: {e}")
        return

    jt = _job_type(job, name)

    if jt != "ROI_SCAN":
        # Not our executor job type -> mark failed w/ needs
        failed_name = f"{os.path.splitext(name)[0]}.FAILED.{_utc_stamp()}.json"
        _move(job_path, os.path.join(outbox_done, failed_name))
        _write_json(
            os.path.join(needs_dir, f"{os.path.splitext(name)[0]}_needs.json"),
            {
                "job_file": name,
                "job_type": jt,
                "missing": ["executor"],
                "hint": f"Ingen executor for job_type={jt}. Legg til handler i worker/task_router.py",
                "timestamp_utc": _utc_iso(),
            },
        )
        _append_log(autorun_log_path, f"[{_utc_iso()}] {jt} -> FAILED (no executor) ({name})")
        return

    # ROI_SCAN executor
    result = run_roi_scan(job)

    if result.ok:
        main_out, stamped_out = _result_paths(results_dir)
        _write_text(main_out, result.markdown)
        _write_text(stamped_out, result.markdown)

        done_name = f"{os.path.splitext(name)[0]}.DONE.{_utc_stamp()}.json"
        _move(job_path, os.path.join(outbox_done, done_name))

        _append_log(autorun_log_path, f"[{_utc_iso()}] ROI_SCAN -> DONE ({name}) wrote ROI_PLAN.md")
    else:
        failed_name = f"{os.path.splitext(name)[0]}.FAILED.{_utc_stamp()}.json"
        _move(job_path, os.path.join(outbox_done, failed_name))

        if result.needs:
            _write_json(
                os.path.join(needs_dir, f"{os.path.splitext(name)[0]}_needs.json"),
                {
                    "job_file": name,
                    "job_type": "ROI_SCAN",
                    "needs": result.needs,
                    "error": result.error,
                    "timestamp_utc": _utc_iso(),
                },
            )

        _append_log(autorun_log_path, f"[{_utc_iso()}] ROI_SCAN -> FAILED ({name}) {result.error or ''}".rstrip())


def main() -> None:
    outbox_dir = os.getenv("IDA_OUTBOX_DIR", "agent_outbox")
    results_dir = os.getenv("IDA_RESULTS_DIR", "agent_results")
    outbox_done = os.getenv("IDA_DONE_DIR", "agent_outbox_done")
    autorun_log = os.getenv("IDA_AUTORUN_LOG", "ops/logs/AUTORUN_LOG.md")
    needs_dir = os.getenv("IDA_NEEDS_DIR", "ops/needs")

    _ensure_dir(outbox_dir)
    _ensure_dir(results_dir)
    _ensure_dir(outbox_done)
    _ensure_dir(os.path.dirname(autorun_log))
    _ensure_dir(needs_dir)

    jobs = _list_jobs(outbox_dir)
    if not jobs:
        _append_log(autorun_log, f"[{_utc_iso()}] ROI_SCAN tick: no jobs")
        return

    # Process at most 1 per run (stable + avoids rate limits)
    process_one(jobs[0], outbox_done, results_dir, needs_dir, autorun_log)


if __name__ == "__main__":
    main()
