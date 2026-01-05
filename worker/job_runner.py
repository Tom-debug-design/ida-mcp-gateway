from __future__ import annotations
import os
import traceback
from datetime import datetime, timezone

from core.config import OUTBOX_DIR, RESULTS_DIR, OPS_LOG_DIR, MAX_JOBS_PER_RUN
from core.io_utils import ensure_dir, read_json, write_json, write_text, utc_now_iso
from core.job_schema import Job
from core.llm_client import llm_text


SYSTEM_CORE = """\
Du er IDA V3. Du skal levere konkret output som gir ROI.
Ingen fantasi. Hvis du mangler proof (repo/sha/filtekst), skriv IKKE at noe er publisert/committed.
Svar med: 1) hva du produserte, 2) hvor filen ligger, 3) neste steg.
Ingen markedsføring av IDA som produkt. Vi selger produkter/tjenester, ikke motoren.
"""


def list_outbox_jobs() -> list[str]:
    if not os.path.isdir(OUTBOX_DIR):
        return []
    files = [f for f in os.listdir(OUTBOX_DIR) if f.endswith(".json")]
    files.sort()  # FIFO-ish hvis job_id har timestamp
    return [os.path.join(OUTBOX_DIR, f) for f in files]


def log_ops(line: str) -> None:
    ensure_dir(OPS_LOG_DIR)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(OPS_LOG_DIR, f"{today}.md")
    prefix = datetime.now(timezone.utc).strftime("%H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"- [{prefix}Z] {line}\n")


def run_job(job_path: str) -> None:
    raw = read_json(job_path)
    job = Job.from_dict(raw)

    job.status = "started"
    job.updated_at = utc_now_iso()
    write_json(job_path, job.to_dict())
    log_ops(f"JOB started: {job.job_id} ({os.path.basename(job_path)})")

    # En “produktiv” default job: lag en ROI-plan/next-batch forslagfil.
    # Dette er nyttig i seg selv, og kan senere kobles til repo-write workflows.
    prompt = f"""
Oppgave: {job.description}

Leveransekrav:
- Skriv et konkret, kort "next_batch" forslag med maks 10 tiltak.
- Hvert tiltak: (P0/P1/P2), forventet ROI, risiko, og helt konkret handling.
- Output skal være ren markdown, ingen bullshit.
"""

    result = llm_text(prompt, system=SYSTEM_CORE).text

    ensure_dir(RESULTS_DIR)
    out_md = os.path.join(RESULTS_DIR, f"{job.job_id}_output.md")
    write_text(out_md, result)

    job.status = "completed"
    job.updated_at = utc_now_iso()
    job.output_files = list(set(job.output_files + [out_md]))
    write_json(job_path, job.to_dict())
    log_ops(f"JOB completed: {job.job_id} -> {out_md}")


def main() -> None:
    ensure_dir(OUTBOX_DIR)
    ensure_dir(RESULTS_DIR)

    jobs = list_outbox_jobs()
    if not jobs:
        log_ops("No jobs in outbox.")
        return

    # SAFE MODE: 1 jobb per run
    to_run = jobs[: max(1, MAX_JOBS_PER_RUN)]

    for job_path in to_run:
        try:
            run_job(job_path)
        except Exception as e:
            tb = traceback.format_exc()
            # marker failed
            try:
                raw = read_json(job_path)
                job = Job.from_dict(raw)
                job.status = "failed"
                job.updated_at = utc_now_iso()
                write_json(job_path, job.to_dict())
            except Exception:
                pass
            log_ops(f"JOB failed: {os.path.basename(job_path)} error={e}")
            ensure_dir(RESULTS_DIR)
            write_text(os.path.join(RESULTS_DIR, f"{os.path.basename(job_path)}.error.txt"), tb)


if __name__ == "__main__":
    main()
