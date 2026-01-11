# worker/task_router.py
# IDA Outbox Task Router (idiotsikkert)
# - Plukker jobber fra agent_outbox (FIFO)
# - Kaller executor hvis finnes
# - Hvis ukjent task: lager ALWAYS et resultat + flytter jobben til done som FAILED_unknown_task
# - Skal aldri kræsje workflowen: exit code 0 uansett

from __future__ import annotations

import os
import sys
import json
import time
import traceback
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# -------------------------
# Config / Paths
# -------------------------

def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None and str(v).strip() != "" else default


OUTBOX_DIR = Path(_env("IDA_OUTBOX_DIR", "agent_outbox"))
DONE_DIR = Path(_env("IDA_DONE_DIR", "agent_outbox_done"))
RESULTS_DIR = Path(_env("IDA_RESULTS_DIR", "agent_results"))
OPS_LOG = Path(_env("IDA_OPS_LOG", "ops/logs/outbox_worker.log"))

MAX_JOBS_PER_RUN = int(_env("IDA_MAX_JOBS_PER_RUN", "20"))  # safety
SLEEP_BETWEEN_JOBS_SEC = float(_env("IDA_SLEEP_BETWEEN_JOBS_SEC", "0.1"))

# Optional: hvis du vil at routeren skal skrive en "heartbeat" hver run:
WRITE_RUN_HEARTBEAT = _env("IDA_WRITE_RUN_HEARTBEAT", "true").lower() in ("1", "true", "yes")


# -------------------------
# Logging
# -------------------------

def _setup_logging() -> None:
    OPS_LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(OPS_LOG, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _ts_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# -------------------------
# Job model
# -------------------------

@dataclass
class Job:
    path: Path
    data: Dict[str, Any]
    task: str

    @property
    def id_hint(self) -> str:
        # used for filenames; stable-ish
        base = self.path.stem
        # remove dots to avoid weird names
        return base.replace(".", "_")


# -------------------------
# IO helpers
# -------------------------

def _read_json(p: Path) -> Dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_text(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        f.write(text)


def _write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _safe_move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        src.replace(dst)  # atomic-ish
    except Exception:
        # fallback copy+delete
        dst.write_bytes(src.read_bytes())
        src.unlink(missing_ok=True)


# -------------------------
# Job scanning
# -------------------------

def _list_jobs_fifo(outbox: Path) -> list[Path]:
    if not outbox.exists():
        return []
    files = []
    for p in outbox.iterdir():
        if p.is_file() and p.suffix.lower() == ".json":
            files.append(p)
    # FIFO = eldste først: mtime
    files.sort(key=lambda x: x.stat().st_mtime)
    return files


def _load_job(p: Path) -> Job:
    data = _read_json(p)
    task = str(data.get("task", "UNKNOWN") or "UNKNOWN").strip()
    if task == "":
        task = "UNKNOWN"
    return Job(path=p, data=data, task=task)


# -------------------------
# Executors
# -------------------------

def _try_run_known_executor(job: Job) -> Tuple[bool, str]:
    """
    Returns: (handled, message)
      - handled=True means we executed something (success or fail), and produced result(s).
      - handled=False means no executor mapping exists for this task.
    """
    task_upper = job.task.strip().upper()

    # Mapping: legg til flere når du vil – men UNKNOWN skal aldri stoppe verden.
    # Vi gjør imports inne i funksjonen så det ikke kræsjer om en modul mangler.
    if task_upper == "ROI_SCAN":
        try:
            from worker.roi_scan import run_roi_scan  # type: ignore
        except Exception:
            # fallback hvis funksjonen heter noe annet i din kode
            try:
                import worker.roi_scan as roi_scan  # type: ignore
                run_roi_scan = getattr(roi_scan, "main", None) or getattr(roi_scan, "run", None)
                if run_roi_scan is None:
                    raise RuntimeError("roi_scan: no run_roi_scan/main/run found")
            except Exception as e:
                return True, f"ROI_SCAN executor import failed: {e}"

        # Kjør ROI scan
        try:
            run_roi_scan(job.data, RESULTS_DIR)  # forventet signatur: (job_data, results_dir)
            return True, "ROI_SCAN executed."
        except TypeError:
            # hvis din roi_scan ikke tar args; prøv uten
            try:
                run_roi_scan()  # type: ignore
                return True, "ROI_SCAN executed (no-arg)."
            except Exception as e:
                return True, f"ROI_SCAN execution failed: {e}"
        except Exception as e:
            return True, f"ROI_SCAN execution failed: {e}"

    # Eksempel på andre task-typer (hvis de finnes i mappa tasks/)
    # Du kan legge disse til senere uten å røre fallbacken:
    # if task_upper == "WEB_SEARCH": ...
    # if task_upper == "DAILY_JOB": ...

    return False, f"No executor mapping for task={job.task}"


def _fallback_unknown(job: Job, reason: str) -> str:
    """
    Always produce a visible result file for UNKNOWN tasks.
    Returns result filename.
    """
    ts = _ts_compact()
    result_name = f"UNKNOWN_TASK_{job.id_hint}_{ts}.md"
    result_path = RESULTS_DIR / result_name

    body = []
    body.append(f"# UNKNOWN TASK HANDLED (fallback)\n")
    body.append(f"- time: {_utc_now_str()}")
    body.append(f"- job_file: `{job.path.as_posix()}`")
    body.append(f"- task: `{job.task}`")
    body.append(f"- reason: `{reason}`\n")
    body.append("## Raw job JSON\n")
    body.append("```json\n" + json.dumps(job.data, ensure_ascii=False, indent=2) + "\n```\n")

    _write_text(result_path, "".join(body))
    logging.warning(f"Fallback wrote result: {result_path.as_posix()}")
    return result_name


# -------------------------
# Processing
# -------------------------

def _mark_done(job: Job, status: str, note: str = "") -> Path:
    """
    Move job JSON into DONE_DIR with status in filename.
    """
    ts = _ts_compact()
    safe_status = status.replace(" ", "_")
    dst_name = f"{job.id_hint}.{safe_status}.{ts}.json"
    dst = DONE_DIR / dst_name

    # optionally enrich job with metadata before moving
    try:
        job.data["_router"] = {
            "time_utc": _utc_now_str(),
            "task": job.task,
            "status": status,
            "note": note[:3000],
        }
        # write temp then move original? simplest: overwrite original with enriched
        _write_json(job.path, job.data)
    except Exception:
        pass

    _safe_move(job.path, dst)
    return dst


def _write_run_heartbeat() -> None:
    # Light, harmless proof the runner is alive
    hb = RESULTS_DIR / "RUNNER_HEARTBEAT.md"
    txt = f"# Runner heartbeat\n\nLast run: {_utc_now_str()}\n"
    _write_text(hb, txt)


def process_one(job_path: Path) -> None:
    job = _load_job(job_path)
    logging.info(f"Picked job: {job.path.name} task={job.task}")

    # Try executor
    handled, msg = _try_run_known_executor(job)

    if not handled:
        # Unknown task => ALWAYS produce output + mark done
        result_file = _fallback_unknown(job, msg)
        done_path = _mark_done(job, "FAILED_unknown_task", f"{msg} | result={result_file}")
        logging.warning(f"UNKNOWN -> FAILED_unknown_task moved to {done_path.name}")
        return

    # If handled=True, we might still have "execution failed" in msg.
    # We decide status based on msg heuristic (idiotsikkert):
    lower = msg.lower()
    if "failed" in lower or "error" in lower or "exception" in lower or "import failed" in lower:
        # Still produce an explicit result file, so you see WHY it failed.
        ts = _ts_compact()
        result_name = f"TASK_FAILED_{job.task}_{job.id_hint}_{ts}.md".replace(" ", "_")
        result_path = RESULTS_DIR / result_name
        _write_text(
            result_path,
            f"# TASK FAILED\n\n- time: {_utc_now_str()}\n- task: `{job.task}`\n- job: `{job.path.name}`\n\n## Message\n{msg}\n\n## Raw job JSON\n```json\n{json.dumps(job.data, ensure_ascii=False, indent=2)}\n```\n",
        )
        done_path = _mark_done(job, "FAILED_executor_error", f"{msg} | result={result_name}")
        logging.error(f"{job.task} -> FAILED_executor_error moved to {done_path.name}")
        return

    done_path = _mark_done(job, "DONE", msg)
    logging.info(f"{job.task} -> DONE moved to {done_path.name}")


def main() -> int:
    _setup_logging()

    # Ensure dirs exist
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    OPS_LOG.parent.mkdir(parents=True, exist_ok=True)

    logging.info("=== task_router tick start ===")
    logging.info(f"OUTBOX={OUTBOX_DIR.as_posix()} DONE={DONE_DIR.as_posix()} RESULTS={RESULTS_DIR.as_posix()}")

    if WRITE_RUN_HEARTBEAT:
        try:
            _write_run_heartbeat()
        except Exception as e:
            logging.warning(f"Could not write heartbeat: {e}")

    jobs = _list_jobs_fifo(OUTBOX_DIR)
    if not jobs:
        logging.info("No jobs in outbox.")
        logging.info("=== task_router tick end ===")
        return 0

    count = 0
    for p in jobs:
        # Safety cap
        if count >= MAX_JOBS_PER_RUN:
            logging.warning(f"Max jobs per run reached ({MAX_JOBS_PER_RUN}). Stop.")
            break

        try:
            process_one(p)
        except Exception as e:
            # HARD fallback: never crash the workflow
            logging.error(f"Process job crashed: {p.name} err={e}")
            logging.error(traceback.format_exc())

            # Try to salvage: move job to done + write crash report
            try:
                job = _load_job(p)
                ts = _ts_compact()
                crash_name = f"ROUTER_CRASH_{job.id_hint}_{ts}.md"
                crash_path = RESULTS_DIR / crash_name
                _write_text(
                    crash_path,
                    f"# ROUTER CRASH\n\n- time: {_utc_now_str()}\n- job: `{p.name}`\n- task: `{job.task}`\n\n## Exception\n```\n{traceback.format_exc()}\n```\n",
                )
                done_path = _mark_done(job, "FAILED_router_crash", f"router crashed | result={crash_name}")
                logging.error(f"Moved crashed job to {done_path.name}")
            except Exception as e2:
                logging.error(f"Could not salvage crashed job {p.name}: {e2}")

        count += 1
        time.sleep(SLEEP_BETWEEN_JOBS_SEC)

    logging.info(f"Processed jobs this tick: {count}")
    logging.info("=== task_router tick end ===")
    return 0


if __name__ == "__main__":
    # IMPORTANT: never exit nonzero (GitHub Actions should not flip red because worker had a task issue)
    try:
        sys.exit(main())
    except Exception:
        # mega-hard fallback
        _setup_logging()
        logging.error("FATAL: task_router main crashed, but forcing exit 0.")
        logging.error(traceback.format_exc())
        sys.exit(0)
