from worker.roi_scan import handle_roi_scan

SUPPORTED_JOB_TYPES = {
    "ROI_SCAN": handle_roi_scan,
}

def route_job(job_type: str):
    if job_type not in SUPPORTED_JOB_TYPES:
        raise ValueError(
            f"Unknown job type: {job_type}. "
            f"Supported: {list(SUPPORTED_JOB_TYPES.keys())}"
        )
    return SUPPORTED_JOB_TYPES[job_type]

