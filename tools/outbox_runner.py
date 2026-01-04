import os
import time
import json
import shutil
from pathlib import Path
from datetime import datetime

OUTBOX = Path("agent_outbox")
PROCESSING = OUTBOX / "_processing"
DONE = OUTBOX / "_done"
FAILED = OUTBOX / "_failed"

RESULTS = Path("agent_results")
LOGDIR = Path("ops/logs")
RUNLOG = LOGDIR / "runner.log"

BUDGET_SECONDS = int(os.getenv("RUN_BUDGET_SECONDS", "120"))
SAFETY_MARGIN = 10  # sek, for å rekke commit/push

def log(msg: str) -> None:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}\n"
    RUNLOG.write_text(RUNLOG.read_text() + line if RUNLOG.exists() else line)

def ensure_dirs():
    for p in [OUTBOX, PROCESSING, DONE, FAILED, RESULTS, LOGDIR]:
        p.mkdir(parents=True, exist_ok=True)

def list_fifo_jobs():
    # FIFO basert på filnavn (job-autogen-YYYYMMDD-HHMMSS.json) eller mtime fallback
    files = [p for p in OUTBOX.glob("*.json") if p.is_file()]
    # sortér stabilt: først navn, så mtime
    files.sort(key=lambda p: (p.name, p.stat().st_mtime))
    return files

def move_job(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        # unik suffix hvis kollisjon
        dest = dest_dir / f"{src.stem}-{int(time.time())}{src.suffix}"
    shutil.move(str(src), str(dest))
    return dest

def write_failure(job_path: Path, err: str):
    fail_log = LOGDIR / f"job_failed_{job_path.stem}.log"
    fail_log.write_text(err)

def execute_job(job: dict) -> dict:
    """
    HER: kobler du på ekte jobblogikk.
    Foreløpig: dummy-output som beviser flyt.
    """
    task = job.get("task", "UNKNOWN")
    # eksempel: skriv en resultfil
    out = {
        "task": task,
        "status": "ok",
        "ts": datetime.utcnow().isoformat() + "Z",
        "notes": "Executed by outbox_runner",
    }
    return out

def main():
    ensure_dirs()

    start = time.time()
    deadline = start + BUDGET_SECONDS - SAFETY_MARGIN
    processed = 0

    jobs = list_fifo_jobs()
    if not jobs:
        log("No jobs in outbox. Exiting.")
        return

    log(f"Start run. budget={BUDGET_SECONDS}s, jobs_in_outbox={len(jobs)}")

    for job_file in jobs:
        if time.time() > deadline:
            log("Budget reached. Stopping this run.")
            break

        # flytt først til processing (hindrer dobbeltkjøring)
        processing_path = move_job(job_file, PROCESSING)
        log(f"Picked job FIFO: {processing_path.name}")

        try:
            job = json.loads(processing_path.read_text(encoding="utf-8"))
            result = execute_job(job)

            # skriv resultat
            RESULTS.mkdir(parents=True, exist_ok=True)
            result_path = RESULTS / f"{processing_path.stem}.result.json"
            result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

            # flytt til done
            move_job(processing_path, DONE)
            processed += 1
            log(f"Job OK: {processing_path.name}")

        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            write_failure(processing_path, err)
            # flytt til failed (ikke blokkér andre jobber)
            move_job(processing_path, FAILED)
            processed += 1
            log(f"Job FAIL: {processing_path.name} -> {err}")

    log(f"Run complete. processed={processed}")

if __name__ == "__main__":
    main()
