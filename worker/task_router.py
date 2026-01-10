from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Optional handlers (import-safe)
try:
    from worker.roi_scan import handle_roi_scan  # type: ignore
except Exception:
    handle_roi_scan = None  # type: ignore


@dataclass
class Paths:
    outbox: Path
    done: Path
    results: Path
    ops_log: Path


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    _safe_mkdir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _append_log(log_path: Path, line: str) -> None:
    _safe_mkdir(log_path.parent)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def _normalize_job_type(job: Dict[str, Any], filename: str = "") -> str:
    """
    Accept EVERYTHING:
      - job_type (preferred)
      - task      (common)
      - type      (older)
      - action    (some generators)
    Also tries to infer from filename or job content.
    """
    raw = (
        job.get("job_type")
        or job.get("task")
        or job.get("type")
        or job.get("action")
        or job.get("kind")
        or ""
    )

    s = str(raw).strip().upper().replace("-", "_").replace(" ", "_")

    # Alias map (future-proof)
    aliases = {
        "ROI": "ROI_SCAN",
        "ROISCAN": "ROI_SCAN",
        "ROI_SCAN": "ROI_SCAN",
        "ROI-SCAN": "ROI_SCAN",
        "ROI_SCAN_V1": "ROI_SCAN",
        "ROI_CHECK": "ROI_SCAN",
    }
    if s in aliases:
        return aliases[s]

    # Infer from filename (last-resort)
    fn = filename.lower()
    if "roi" in fn and "scan" in fn:
        return "ROI_SCAN"

    # Infer from content keys (last-resort)
    # (you can extend this without breaking old jobs)
    if "roi" in job or "keywords" in job or "market" in job:
        # not perfect, but better than failing
        return "ROI_SCAN"

    return s or "UNKNOWN"


def _result_filename(job_file: Path) -> str:
    # Example: job-autogen-20260110-165356.json -> result-job-autogen-....json
    return f"result-{job_file.name}"


def _move_to_done(job_file: Path, done_dir: Path) -> Path:
    _safe_mkdir(done_dir)
    target = done_dir / job_file.name
    # overwrite-safe
    if target.exists():
        target = done_dir / f"{job_file.stem}-{int(time.time())}{job_file.suffix}"
    shutil.move(str(job_file), str(target))
    return target


def _dispatch(job: Dict[str, Any], job_type: str) -> Dict[str, Any]:
    """
    Central dispatcher.
    Never throws: always returns a result dict.
    """
    if job_type == "ROI_SCAN" and handle_roi_scan is not None:
        return handle_roi_scan(job, {})  # needs dict not used in many handlers

    # Unknown / missing handler => produce a structured failure result
    return {
        "job_id": job.get("job_id", "unknown"),
        "job_type": job_type,
        "status": "FAILED_UNKNOWN",
        "reason": f"No executor registered for job_type={job_type!r}",
        "details": {
            "seen_keys": sorted(list(job.keys()))[:80],
            "hint": "Ensure generator emits job_type/task/type/action that matches a handler. "
                    "Router accepts many schemas, but still needs a handler name.",
        },
        "ts": _now_iso(),
    }


def main() -> None:
    # Environment-driven directories (safe defaults)
    outbox_dir = Path(os.getenv("IDA_OUTBOX_DIR", "agent_outbox"))
    done_dir = Path(os.getenv("IDA_DONE_DIR", "agent_outbox_done"))
    results_dir = Path(os.getenv("IDA_RESULTS_DIR", "agent_results"))
    ops_log = Path(os.getenv("IDA_OPS_LOG", "ops/logs/outbox_worker.log"))

    paths = Paths(outbox=outbox_dir, done=done_dir, results=results_dir, ops_log=ops_log)

    _safe_mkdir(paths.outbox)
    _safe_mkdir(paths.done)
    _safe_mkdir(paths.results)
    _safe_mkdir(paths.ops_log.parent)

    job_files = sorted(paths.outbox.glob("*.json"))
    if not job_files:
        _append_log(paths.ops_log, f"[{_now_iso()}] ROI_SCAN tick: no jobs")
        return

    for jf in job_files:
        try:
            job = _read_json(jf)
        except Exception as e:
            # Bad JSON => move to done + create failure result
            _append_log(paths.ops_log, f"[{_now_iso()}] FAILED reading {jf.name}: {e}")
            result = {
                "job_id": "unknown",
                "job_type": "UNKNOWN",
                "status": "FAILED_BAD_JSON",
                "reason": f"Could not parse JSON: {e}",
                "file": jf.name,
                "ts": _now_iso(),
            }
            _write_json(paths.results / _result_filename(jf), result)
            _move_to_done(jf, paths.done)
            continue

        job_type = _normalize_job_type(job, filename=jf.name)

        # Always produce a result; never crash
        result = _dispatch(job, job_type)

        # Persist result + move job to done
        _write_json(paths.results / _result_filename(jf), result)
        _move_to_done(jf, paths.done)

        _append_log(
            paths.ops_log,
            f"[{_now_iso()}] {job_type} -> {result.get('status')} ({jf.name})",
        )


if __name__ == "__main__":
    main()
