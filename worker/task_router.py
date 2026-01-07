import json
from pathlib import Path
from worker.roi_scan import run_roi_scan

OUTBOX = Path("agent_outbox")
DONE = Path("agent_outbox_done")

def dispatch(job_path: Path):
    with open(job_path, "r", encoding="utf-8") as f:
        job = json.load(f)

    task = job.get("task")

    if task == "ROI_SCAN":
        run_roi_scan(job)
    else:
        raise ValueError(f"Unknown task: {task}")

    DONE.mkdir(exist_ok=True)
    job_path.rename(DONE / job_path.name)

def main():
    for job in OUTBOX.glob("*.json"):
        dispatch(job)

if __name__ == "__main__":
    main()
