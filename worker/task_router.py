# worker/task_router.py
from __future__ import annotations

import json
import os
import shutil
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# ---------- config ----------
DEFAULT_OUTBOX_DIR = os.getenv("IDA_OUTBOX_DIR", "agent_outbox")
DEFAULT_DONE_DIR = os.getenv("IDA_DONE_DIR", "agent_outbox_done")
DEFAULT_RESULTS_DIR = os.getenv("IDA_RESULTS_DIR", "agent_results")
DEFAULT_OPS_LOG = os.getenv("IDA_OPS_LOG", "ops/logs/outbox_worker.log")


# ---------- utils ----------
def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _append_log(repo_root: Path, line: str) -> None:
    log_path = repo_root / DEFAULT_OPS_LOG
    _mkdir(log_path.parent)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_move(src: Path, dst: Path) -> None:
    _mkdir(dst.parent)
    if dst.exists():
        dst.unlink()
    shutil.move(str(src), str(dst))


def _pick_oldest_json(outbox_dir: Path) -> Optional[Path]:
    files = sorted(outbox_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return files[0] if files else None


# ---------- executor routing ----------
@dataclass
class RouteResult:
    ok: bool
    status: str  # SUCCESS / FAILED
    message: str


def _run_executor(task: str, job: Dict[str, Any], repo_root: Path) -> RouteResult:
    """
    Central router. Add new executors here.
    """
    task = (task or "").strip().upper()

    if task == "ROI_SCAN":
        # Lazy import so missing modules don't break other tasks
        from executors.roi_scan import run as roi_run  # type: ignore

        res = roi_run(job, repo_root=repo_root)
        return RouteResult(ok=res.ok, status="SUCCESS" if res.ok else "FAILED", message=res.message)

    # Unknown task => FAILED (no executor)
    return RouteResult(ok=False, status="FAILED", message="no executor")


# ---------- main worker ----------
def main() -> int:
    repo_root = Path(os.getenv("GITHUB_WORKSPACE", ".")).resolve()

    outbox_dir = (repo_root / DEFAULT_OUTBOX_DIR).resolve()
    done_dir = (repo_root / DEFAULT_DONE_DIR).resolve()
    results_dir = (repo_root / DEFAULT_RESULTS_DIR).resolve()

    _mkdir(outbox_dir)
    _mkdir(done_dir)
    _mkdir(results_dir)

    job_file = _pick_oldest_json(outbox_dir)
    if not job_file:
        _append_log(repo_root, f"[{_utc_now()}] ROI_SCAN tick: no jobs")
        return 0

    try:
        job = _load_json(job_file)
        task = str(job.get("task", "UNKNOWN"))
        started = _utc_now()

        rr = _run_executor(task, job, repo_root)

        # Move to done with status suffix (keeps your existing naming style)
        base = job_file.stem
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        done_name = f"{base}.{rr.status}.{ts}.json"
        done_path = done_dir / done_name

        _safe_move(job_file, done_path)

        _append_log(
            repo_root,
            f"[{started}] {task} -> {rr.status} ({rr.message}) ({done_name})"
        )

        return 0 if rr.ok else 1

    except Exception as e:
        # If something explodes, don’t lose the job: move it to done as FAILED.
        try:
            base = job_file.stem if job_file else "job"
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            done_name = f"{base}.FAILED.{ts}.json"
            done_path = done_dir / done_name
            if job_file and job_file.exists():
                _safe_move(job_file, done_path)
        except Exception:
            pass

        _append_log(repo_root, f"[{_utc_now()}] WORKER CRASH: {e}\n{traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
