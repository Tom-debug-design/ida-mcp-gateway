# tools/job_schema.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional
import json

REQUIRED_TOP_KEYS = {"id", "type", "payload"}
OPTIONAL_TOP_KEYS = {"output", "meta"}

@dataclass
class Job:
    id: str
    type: str
    payload: Dict[str, Any]
    output: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None

class JobSchemaError(Exception):
    pass

def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise JobSchemaError(msg)

def parse_job(raw: Dict[str, Any]) -> Job:
    _assert(isinstance(raw, dict), "Job must be a JSON object")

    keys = set(raw.keys())
    missing = REQUIRED_TOP_KEYS - keys
    _assert(not missing, f"Missing required keys: {sorted(list(missing))}")

    unknown = keys - (REQUIRED_TOP_KEYS | OPTIONAL_TOP_KEYS)
    _assert(not unknown, f"Unknown keys not allowed: {sorted(list(unknown))}")

    job_id = raw["id"]
    job_type = raw["type"]
    payload = raw["payload"]

    _assert(isinstance(job_id, str) and job_id.strip(), "id must be a non-empty string")
    _assert(isinstance(job_type, str) and job_type.strip(), "type must be a non-empty string")
    _assert(isinstance(payload, dict), "payload must be an object")

    output = raw.get("output")
    meta = raw.get("meta")

    if output is not None:
        _assert(isinstance(output, dict), "output must be an object if present")
        # Optional but recommended: output.path
        if "path" in output:
            _assert = output["path"]
            _assert(isinstance(_R, str) and _R.strip(), "output.path must be a non-empty string")

    if meta is not None:
        _assert(isinstance(meta, dict), "meta must be an object if present")

    return Job(
        id=job_id.strip(),
        type=job_type.strip(),
        payload=payload,
        output=output,
        meta=meta,
    )

def load_job_from_file(path: str) -> Job:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return parse_job(raw)
