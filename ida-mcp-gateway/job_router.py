from __future__ import annotations

from worker.roi_scan import handle_roi_scan


def dispatch(job: dict, needs: dict) -> dict:
    # Accept multiple schema variants:
    # - job_type (preferred)
    # - task (what the generator currently emits)
    # - type  (older/alternate)
    raw_type = (
        job.get("job_type")
        or job.get("task")
        or job.get("type")
        or ""
    )
    job_type = str(raw_type).strip().upper()

    if job_type == "ROI_SCAN":
        return handle_roi_scan(job, needs)

    return {
        "job_id": job.get("job_id", "unknown"),
        "job_type": job_type,
        "status": "FAILED",
        "reason": f"Unknown job type: {job_type!r}. Expected one of: ROI_SCAN",
        "details": {
            "seen_keys": sorted(list(job.keys()))[:50],
            "hint": "Provide job_type (preferred) or task/type in the job JSON.",
        },
    }
