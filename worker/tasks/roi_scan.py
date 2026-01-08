# worker/tasks/roi_scan.py
from __future__ import annotations

import os
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Tuple, Optional

import requests


@dataclass
class RoiScanResult:
    ok: bool
    markdown: str
    needs: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _call_openai_markdown(prompt: str) -> Tuple[bool, str, str]:
    """
    Calls OpenAI using REST (requests), returns: (ok, markdown, error)
    Uses: OPENAI_API_KEY, OPENAI_MODEL
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "").strip() or "gpt-4.1-mini"

    if not api_key:
        return False, "", "Missing OPENAI_API_KEY"

    # Responses API (modern). If your account blocks it, we fail cleanly and report needs.
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "input": prompt,
        "temperature": 0.2,
        "max_output_tokens": 1200,
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        if r.status_code >= 400:
            return False, "", f"OpenAI HTTP {r.status_code}: {r.text[:500]}"
        data = r.json()

        # Try to extract text from common response shapes
        text = ""
        if isinstance(data, dict):
            # responses api: output -> content -> text
            out = data.get("output")
            if isinstance(out, list) and out:
                # Find first output_text-like content
                for item in out:
                    content = item.get("content") if isinstance(item, dict) else None
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") in ("output_text", "text"):
                                text = c.get("text", "") or ""
                                break
                        if text:
                            break

            # Fallback
            if not text:
                text = data.get("text", "") or ""

        text = (text or "").strip()
        if not text:
            return False, "", "OpenAI returned empty text"
        return True, text, ""
    except Exception as e:
        return False, "", f"OpenAI call exception: {type(e).__name__}: {e}"


def run_roi_scan(job: Dict[str, Any]) -> RoiScanResult:
    """
    ROI_SCAN executor.
    Input: job dict (from json in agent_outbox)
    Output: markdown plan in Norwegian, actionable.
    """
    # Minimal required fields (we’re tolerant)
    goal = (job.get("goal") or job.get("mål") or job.get("objective") or "").strip()
    context = job.get("context") or job.get("bakgrunn") or ""
    constraints = job.get("constraints") or job.get("rammer") or ""
    timeframe = job.get("timeframe") or job.get("tidslinje") or "nå"

    if not goal:
        return RoiScanResult(
            ok=False,
            markdown="",
            needs={
                "missing": ["goal"],
                "hint": "Legg inn goal/mål i ROI_SCAN-jobben (hva skal IDA levere).",
                "example_job": {
                    "job_type": "ROI_SCAN",
                    "goal": "Lag ROI-plan for API-resale bootstrap som kan gi inntekt raskt",
                    "timeframe": "48 timer",
                    "constraints": "maks 2 timers manuelt arbeid per dag"
                }
            },
            error="Missing required field: goal"
        )

    # Build a single sharp prompt (no essay-mode)
    prompt = f"""
Du er IDA. Svar på norsk. Lag en ROI-plan som er HANDLINGSRETTET og kortfattet.
Mål: {goal}
Tidslinje: {timeframe}

Kontekst:
{context}

Rammer/constraints:
{constraints}

Krav:
- Maks 1 side (Markdown).
- Start med: "## ROI PLAN (IDA)"
- Inkluder:
  1) "Hva vi bygger (1 setning)"
  2) "Første inntekts-vei (konkret)"
  3) "48-timers plan" (punktliste, timebox)
  4) "Metrikker" (hva måles daglig)
  5) "Risiko & kill-criteria" (når vi stopper/endre kurs)
  6) "Neste automatisering IDA gjør alene" (konkret)
- Ikke prat om teori, ikke skriv lange forklaringer.
""".strip()

    ok, md, err = _call_openai_markdown(prompt)

    if not ok:
        return RoiScanResult(
            ok=False,
            markdown="",
            needs={
                "missing": ["openai_api_working"],
                "hint": "OpenAI-kallet feilet. Sjekk OPENAI_API_KEY/OPENAI_MODEL i repo secrets.",
                "error": err,
            },
            error=err,
        )

    # Ensure it looks like a markdown plan
    if "## ROI PLAN" not in md:
        md = "## ROI PLAN (IDA)\n\n" + md

    # Add a small footer with trace
    md += f"\n\n---\nGenerated: {_utc_stamp()} (UTC)\nJob: ROI_SCAN\n"
    return RoiScanResult(ok=True, markdown=md)
