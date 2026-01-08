from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_dirs() -> None:
    Path("agent_results").mkdir(parents=True, exist_ok=True)
    Path("ops/logs").mkdir(parents=True, exist_ok=True)


def _write_text(path: str, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _write_json(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def handle_roi_scan(job: dict, needs: dict) -> dict:
    """
    ROI_SCAN worker.
    Contract:
      - Always writes:
          agent_results/ROI_PLAN.md
          ops/logs/AUTORUN_LOG.md
          agent_results/<job_id>.RESULT.json
      - Returns a dict with status=SUCCESS and artifact paths
    """
    _ensure_dirs()

    job_id = job.get("job_id", "unknown")
    goal = (job.get("goal") or "").strip()
    timeframe = (job.get("timeframe") or "").strip()

    market = (needs.get("market") or "Global").strip()
    budget = (needs.get("budget") or "0").strip()
    preferred_model = (needs.get("preferred_model") or "API resale").strip()
    time_to_first_income = (needs.get("time_to_first_income") or "Under 30 dager").strip()
    legal_scope = (needs.get("legal_scope") or "EU").strip()
    risk_tolerance = (needs.get("risk_tolerance") or "Lav").strip()
    deliverable = (needs.get("deliverable") or "ROI plan").strip()
    target_customer = (needs.get("target_customer") or "Små SaaS/solopreneurs").strip()

    now = _utc_iso()

    # --- ROI PLAN (Markdown) ---
    roi_md = f"""# ROI Plan — {preferred_model}

**Job ID:** {job_id}  
**Generated:** {now}  

## Input
- **Goal:** {goal or "Lag ROI-plan som kan gi inntekt raskt"}
- **Timeframe:** {timeframe or "48 timer (plan) / 30 dager (første inntekt)"}
- **Market:** {market}
- **Budget:** {budget}
- **Legal scope:** {legal_scope}
- **Risk tolerance:** {risk_tolerance}
- **Target customer:** {target_customer}
- **Deliverable:** {deliverable}

---

## 1) Tilbud (det vi selger)
### Produkt: “AI-funksjon inn i ditt SaaS”
**Kjerne:** Du tilbyr en “white-label AI”-backend som de kan kalle via API (chat/support/analyse/tekstoppsummering) uten å bygge det selv.

**Pakker (enkelt og brutalt):**
- **Starter:** €49/mnd — 5k requests/mnd, basis-modell, standard rate limit
- **Pro:** €149/mnd — 25k requests/mnd, logging + enklere “guardrails”
- **Agency:** €399/mnd — 100k requests/mnd, 3 kunder/prosjekter, prioritet + SLA-light

**Upsell (lav friksjon):**
- “Setup-fee” €199–€499 for integrasjon (engangs)
- “Custom prompt + tone” €99/mnd
- “Compliance/PII mode” €99/mnd (EU-friendly)

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
1. **LinkedIn**: SaaS-founders + indiehackers (målrettet DM)
2. **Cold e-post**: finn 30 små SaaS (1–10 ansatte) → enkel pitch
3. **Discord/communities**: indie/saas communities → post “done-for-you AI API”

---

## 4) Outreach-melding (kort)
**Subject:** “Jeg kan gi deg AI-support i produktet ditt på 24t”

Hei {{navn}},  
Jeg lager en liten “white-label AI API” som du kan plugge inn i ditt SaaS for chat/support/svarforslag – uten at dere må bygge/vedlikeholde LLM-stack selv.  
Hvis du vil, kan jeg sette opp en demo i ditt miljø på 24–48t.

Vil du at jeg sender en 2-min demo + pris?

---

## 5) 72t plan (praktisk)
**Dag 1:** Velg 1 usecase (support reply) + endpoint + API key  
**Dag 2:** Lag demo landing + 20–30 outreach (LinkedIn/e-post)  
**Dag 3:** Book 2 calls, tilby “setup-fee” + månedspakke

---

## 6) Suksesskriterie
- **30 kontakter → 3 svar → 1 betalt pilot**
- Mål: **€49–€149 første måned** → bevis → skaler outreach
"""

    _write_text("agent_results/ROI_PLAN.md", roi_md)

    # --- LOG ---
    log_md = f"""# AUTORUN LOG

- **timestamp:** {now}
- **job_id:** {job_id}
- **job_type:** ROI_SCAN
- **status:** SUCCESS
- **artifacts:**
  - agent_results/ROI_PLAN.md
  - agent_results/{job_id}.RESULT.json
  - ops/logs/AUTORUN_LOG.md
"""
    _write_text("ops/logs/AUTORUN_LOG.md", log_md)

    # --- MACHINE RESULT (JSON) ---
    result = {
        "job_id": job_id,
        "job_type": "ROI_SCAN",
        "status": "SUCCESS",
        "generated_at": now,
        "inputs": {
            "goal": goal,
            "timeframe": timeframe,
        },
        "needs": {
            "market": market,
            "budget": budget,
            "preferred_model": preferred_model,
            "time_to_first_income": time_to_first_income,
            "legal_scope": legal_scope,
            "risk_tolerance": risk_tolerance,
            "deliverable": deliverable,
            "target_customer": target_customer,
        },
        "artifacts": [
            "agent_results/ROI_PLAN.md",
            f"agent_results/{job_id}.RESULT.json",
            "ops/logs/AUTORUN_LOG.md",
        ],
        "next": {
            "suggested_job_type": "AUTOGEN",
            "suggested_goal": "Generate next 3 repo actions based on ROI_PLAN",
        },
    }
    _write_json(f"agent_results/{job_id}.RESULT.json", result)

    return result
