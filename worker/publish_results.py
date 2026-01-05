# worker/publish_results.py
# Production: daily append-only ops log for each completed job result.
# Writes:
#  - agent_results/<job_id>.result.json  (existing behavior)
#  - agent_results/DAILY_YYYY-MM-DD.md   (new A2 behavior)

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


RESULTS_DIR = os.environ.get("RESULTS_DIR", "agent_results")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _extract_usage(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tries multiple common shapes:
      - result["usage"] = {"total_tokens":..., "prompt_tokens":..., "completion_tokens":...}
      - result["meta"]["usage"] ...
      - result["provider"]["usage"] ...
    """
    for key_path in (
        ("usage",),
        ("meta", "usage"),
        ("provider", "usage"),
        ("openai", "usage"),
    ):
        cur: Any = result
        ok = True
        for k in key_path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok and isinstance(cur, dict):
            return cur
    return {}


def _extract_cost(result: Dict[str, Any]) -> Optional[float]:
    """
    Tries:
      - result["cost_usd"]
      - result["meta"]["cost_usd"]
      - result["billing"]["cost_usd"]
    """
    candidates = [
        result.get("cost_usd"),
        (result.get("meta") or {}).get("cost_usd") if isinstance(result.get("meta"), dict) else None,
        (result.get("billing") or {}).get("cost_usd") if isinstance(result.get("billing"), dict) else None,
    ]
    for c in candidates:
        f = _safe_float(c)
        if f is not None:
            return f
    return None


def _extract_status(result: Dict[str, Any]) -> str:
    for k in ("status", "state", "result_status"):
        v = result.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    # fallback: if error present -> fail else ok
    if result.get("error") or result.get("exception") or result.get("traceback"):
        return "fail"
    return "ok"


def _extract_job_id(result: Dict[str, Any]) -> str:
    for k in ("job_id", "id", "job", "name", "file"):
        v = result.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return f"job-{_utc_now().strftime('%Y%m%d-%H%M%S')}"


def _extract_reason(result: Dict[str, Any]) -> Optional[str]:
    # Keep it short and safe
    for k in ("reason", "message", "error", "exception"):
        v = result.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().replace("\n", " ")[:160]
    return None


def _format_daily_line(ts: datetime, job_id: str, status: str, tokens: Optional[int], cost: Optional[float], reason: Optional[str]) -> str:
    hhmm = ts.astimezone(timezone.utc).strftime("%H:%M")
    parts = [f"[{hhmm}] job={job_id}", f"status={status}"]
    if tokens is not None:
        parts.append(f"tokens={tokens}")
    if cost is not None:
        parts.append(f"cost=${cost:.6f}")
    if status != "ok" and reason:
        parts.append(f"reason={reason}")
    return "  ".join(parts) + "\n"


def write_result_output(result: Dict[str, Any], filename_hint: Optional[str] = None) -> Dict[str, str]:
    """
    Main entrypoint. Call this after a job is completed (success or fail).
    Writes:
      1) JSON result file
      2) DAILY_YYYY-MM-DD.md append line

    Returns dict of written paths.
    """
    results_dir = Path(RESULTS_DIR)
    _ensure_dir(results_dir)

    ts = _utc_now()
    job_id = _extract_job_id(result)

    # 1) Result JSON file (stable name, no overwrite risk if job_id unique)
    out_name = filename_hint or f"{job_id}.result.json"
    if not out_name.endswith(".result.json"):
        # Keep consistent naming
        out_name = out_name.replace(".json", "") + ".result.json"
    result_path = results_dir / out_name

    # Write JSON atomically-ish
    tmp_path = results_dir / (out_name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    tmp_path.replace(result_path)

    # 2) Daily markdown append-only log
    status = _extract_status(result)
    usage = _extract_usage(result)
    tokens = None
    if isinstance(usage, dict):
        # prefer total_tokens, else sum known fields
        if isinstance(usage.get("total_tokens"), int):
            tokens = int(usage["total_tokens"])
        else:
            pt = usage.get("prompt_tokens")
            ct = usage.get("completion_tokens")
            if isinstance(pt, int) and isinstance(ct, int):
                tokens = int(pt + ct)
    cost = _extract_cost(result)
    reason = _extract_reason(result)

    daily_file = results_dir / f"DAILY_{ts.strftime('%Y-%m-%d')}.md"
    line = _format_daily_line(ts, job_id, status, tokens, cost, reason)

    # IMPORTANT: logging must never break production flow
    try:
        with daily_file.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # swallow logging errors (production rule)
        pass

    return {
        "result_json": str(result_path),
        "daily_log": str(daily_file),
    }
