from __future__ import annotations

from worker.roi_scan import handle_roi_scan


def dispatch(job: dict, needs: dict) -> dict:
    job_type = (job.get("job_type") or "").strip().upper()

    if job_type == "ROI_SCAN":
        return handle_roi_scan(job, needs)

    return {
        "job_id": job.get("job_id", "unknown"),
        "job_type": job_type,
        "status": "FAILED",
        "reason": f"Unknown job type: {job_type}",
    }
