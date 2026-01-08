from __future__ import annotations

from worker.roi_scan import handle_roi_scan


def _norm(s: object) -> str:
    return (str(s) if s is not None else "").strip()


def _detect_job_type(job: dict) -> str:
    """
    Robust detection:
    - prefer explicit fields: job_type / task / type
    - fallback: infer from job_id or source/file if present
    """
    # 1) Explicit fields
    candidates = [
        job.get("job_type"),
        job.get("task"),
        job.get("type"),
    ]
    for c in candidates:
        v = _norm(c)
        if v:
            return v.upper()

    # 2) Fallback: infer from identifiers / file path hints
    hints = " ".join(
        [
            _norm(job.get("job_id")),
            _norm(job.get("id")),
            _norm(job.get("source")),
            _norm(job.get("file")),
            _norm(job.get("path")),
            _norm(job.get("filename")),
        ]
    ).lower()

    # Add more inference rules here if you add more job types later
    if "roi_scan" in hints or "roi-scan" in hints or "roiscan" in hints:
        return "ROI_SCAN"

    return ""


def dispatch(job: dict, needs: dict) -> dict:
    job_type = _detect_job_type(job)

    if job_type == "ROI_SCAN":
        return handle_roi_scan(job, needs)

    # IMPORTANT: keep this as NEEDS_INPUT (not FAILED),
    # because the pipeline can then feed needs and retry cleanly.
    return {
        "job_id": job.get("job_id", "unknown"),
        "job_type": job_type or None,
        "status": "NEEDS_INPUT",
        "reason": "Unknown job type",
        "details": {
            "type": job_type or None,
            "expected_keys_any_of": ["job_type", "task", "type"],
            "supported": ["ROI_SCAN"],
        },
    }
