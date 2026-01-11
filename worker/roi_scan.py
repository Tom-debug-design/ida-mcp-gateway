# worker/roi_scan.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _env(key: str, default: str) -> str:
    v = os.getenv(key, "").strip()
    return v if v else default


def _ensure_dir(path: str) -> None:
    if path:
        os.makedirs(path, exist_ok=True)


def _write_text(path: str, text: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        _ensure_dir(parent)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _append_text(path: str, text: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        _ensure_dir(parent)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)
    except Exception:
        return json.dumps({"error": "failed_to_json_dump"}, indent=2)


@dataclass
class RoiConfig:
    results_dir: str
    ops_log_path: str


def _build_roi_plan_md(job: Dict[str, Any]) -> str:
    created = job.get("created_at") or job.get("time") or _utc_now_iso()
    job_id = job.get("job_id") or job.get("id") or "unknown"

    inp = job.get("input") or {}
    goal = inp.get("goal") or "Lag ROI-plan som kan gi inntekt raskt"
    timeframe = inp.get("timeframe") or "48 timer (plan) / 30 dager (første inntekt)"
    market = inp.get("market") or "Global"
    budget = inp.get("budget") or "0"
    legal_scope = inp.get("legal_scope") or "EU"
    risk = inp.get("risk_tolerance") or "Lav"
    target = inp.get("target_customer") or "Små SaaS/solopreneurs"

    # Her er det helt bevisst MARKDOWN-tekst inne i en Python-string.
    # Den skal skrives til ROI_PLAN.md (ikke være "kode").
    return f"""# ROI Plan — API resale

Job ID: {job_id}  
Generated: {created}

## Input
- Goal: {goal}
- Timeframe: {timeframe}
- Market: {market}
- Budget: {budget}
- Legal scope: {legal_scope}
- Risk tolerance: {risk}
- Target customer: {target}
- Deliverable: ROI plan

---

## 1) Tilbud (det vi selger)

**Produkt:** "AI-funksjon inn i ditt SaaS"

**Kjerne:** Du tilbyr en "white-label AI-backend" som kunden kan kalle via API (chat/support/analyse),
slik at de slipper å bygge LLM-stack selv.

**Pakker (enkelt og brutalt):**
- Starter: €49/mnd — 5k requests/mnd, basis-modell, standard rate limit
- Pro: €149/mnd — 25k requests/mnd, logging + enklere "guardrails"
- Agency: €399/mnd — 100k requests/mnd, 3 kunder/prosjekter, prioritet + SLA-light

**Upsell (lav friksjon):**
- Setup-fee: €199–€499 for integrasjon (engangs)
- Custom prompt + tone: €99/mnd
- Compliance/PII mode: €99/mnd (EU-friendly)

---

## 2) MVP i repoet (hva du faktisk trenger)

**Minimum:**
- 1 endpoint: `/chat` eller `/support_reply`
- API key auth
- Logging: request_count + basic cost estimate
- Simple dashboard/CSV export (senere)

**Teknisk stack forslag (lav friksjon):**
- FastAPI + uvicorn
- 1 provider (OpenAI først)
- SQLite eller JSON-logg (start billig)

---

## 3) Første 3 kundekanaler (0-budsjett)

1. LinkedIn: SaaS-founders + indiehackers (målrettet DM)
2. Cold e-post: finn 30 små SaaS (1–10 ansatte) → enkel pitch
3. Discord/communities: indie/saas communities → post "done-for-you AI API"

---

## 4) Outreach-melding (kort)

**Subject:** "Jeg kan gi deg AI-support i produktet ditt på 24t"

Hei {{{{navn}}}},

Jeg lager en liten "white-label AI API" som du kan plugge inn i ditt SaaS for chat/support,
uten å bygge LLM-stack selv.

Hvis du vil, kan jeg sette opp en demo i ditt miljø på 24–48t.

Vil du at jeg sender en 2-min demo + pris?

---

## 5) 72t plan (praktisk)

- Dag 1: Velg 1 usecase (support reply) + endpoint + API key
- Dag 2: Lag demo landing + 20–30 outreach (LinkedIn/e-post)
- Dag 3: Book 2 calls, tilby "setup-fee" + månedspakke

---

## 6) Suksesskriterie

- 30 kontakter → 3 svar → 1 betalt pilot
- Mål: €49–€149 første måned → bevis → skaler outreach
"""


def _log_line(cfg: RoiConfig, level: str, msg: str, job_id: str) -> None:
    ts = _utc_now_iso()
    _append_text(cfg.ops_log_path, f"{ts} [{level}] ROI_SCAN job_id={job_id} {msg}\n")


def run(job: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Public executor API.
    Entry point: run(...)
    """
    job = job or {}
    job_id = str(job.get("job_id") or job.get("id") or "unknown")

    cfg = RoiConfig(
        results_dir=_env("IDA_RESULTS_DIR", "agent_results"),
        ops_log_path=_env("IDA_OPS_LOG", os.path.join("ops", "logs", "AUTORUN_LOG.md")),
    )

    try:
        _log_line(cfg, "INFO", "start", job_id)

        roi_plan_md = _build_roi_plan_md(job)
        roi_plan_path = os.path.join(cfg.results_dir, "ROI_PLAN.md")
        _write_text(roi_plan_path, roi_plan_md)

        _log_line(cfg, "INFO", f"wrote {roi_plan_path}", job_id)

        return {
            "ok": True,
            "task": "ROI_SCAN",
            "job_id": job_id,
            "time": _utc_now_iso(),
            "deliverables": {
                "agent_results/ROI_PLAN.md": roi_plan_path,
                "ops/logs/AUTORUN_LOG.md": cfg.ops_log_path,
            },
        }

    except Exception as e:
        failed_path = os.path.join(cfg.results_dir, "ROI_FAILED.md")
        text = (
            "# TASK FAILED\n\n"
            f"- time: {_utc_now_iso()}\n"
            "- task: ROI_SCAN\n"
            f"- job: {job_id}\n\n"
            "## Message\n"
            f"{type(e).__name__}: {e}\n\n"
            "## Raw job JSON\n"
            "```json\n"
            f"{_safe_json(job)}\n"
            "```\n"
        )
        _write_text(failed_path, text)
        try:
            _log_line(cfg, "ERROR", f"failed: {type(e).__name__}: {e}", job_id)
        except Exception:
            pass

        return {
            "ok": False,
            "task": "ROI_SCAN",
            "job_id": job_id,
            "time": _utc_now_iso(),
            "error": f"{type(e).__name__}: {e}",
            "failed_path": failed_path,
        }
