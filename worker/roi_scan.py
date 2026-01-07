import os
from pathlib import Path
from providers.openai_provider import ask_openai

RESULTS = Path("agent_results")
RESULTS.mkdir(exist_ok=True)

def run_roi_scan(job: dict):
    prompt = f"""
You are IDA.

Task: ROI Scan

Focus:
{chr(10).join(job.get("focus", []))}

Rules:
{chr(10).join(job.get("rules", []))}

Deliverables:
- Concrete actions
- Repo-ready output
- No theory

Return a practical ROI plan.
"""

    response = ask_openai(prompt)

    out = RESULTS / "ROI_PLAN.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write(response)
