#!/usr/bin/env python3
"""
IDA Outbox Worker
- Reads jobs from agent_outbox/
- Executes a real action (OpenAI analysis) per job
- Writes output to agent_results/
- Moves processed job files to agent_outbox_done/
- Appends a small ops log entry under ops/logs/
"""

import os
import sys
import json
import time
import glob
import shutil
import hashlib
import datetime as dt
from typing import Any, Dict, Optional, Tuple

try:
    import requests  # type: ignore
except Exception:
    requests = None


def utc_now_compact() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")


def safe_mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path: str, content: str) -> None:
    safe_mkdir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def append_text(path: str, content: str) -> None:
    safe_mkdir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)


def read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj: Dict[str, Any]) -> None:
    safe_mkdir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def sha1_short(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


def pick_job_type(job: Dict[str, Any]) -> str:
    for k in ("type", "job_type", "kind", "category"):
        v = job.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "general_insight"


def pick_job_title(job: Dict[str, Any]) -> str:
    for k in ("title", "name", "headline"):
        v = job.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "IDA job"


def pick_job_instructions(job: Dict[str, Any]) -> str:
    for k in ("instructions", "instruction", "prompt", "task", "description"):
        v = job.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "Analyze and produce actionable insights + next suggested jobs."


def openai_chat_completion(prompt: str, model: str, api_key: str, timeout_s: int = 60) -> Tuple[bool, str]:
    """
    Uses OpenAI Chat Completions (requests). No extra deps.
    Returns (ok, text_or_error).
    """
    if requests is None:
        return (False, "requests is not available in this environment.")

    url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "You are IDA. Be direct, practical, and output structured results."},
            {"role": "user", "content": prompt},
        ],
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
        if r.status_code >= 400:
            return (False, f"OpenAI HTTP {r.status_code}: {r.text[:800]}")
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        return (True, text)
    except Exception as e:
        return (False, f"OpenAI request failed: {repr(e)}")


def build_prompt(job: Dict[str, Any], job_path: str) -> str:
    job_type = pick_job_type(job)
    title = pick_job_title(job)
    instr = pick_job_instructions(job)
    job_raw = json.dumps(job, ensure_ascii=False, indent=2)

    return f"""TASK TYPE: {job_type}
TITLE: {title}

INSTRUCTIONS:
{instr}

JOB JSON:
{job_raw}

OUTPUT FORMAT (STRICT):
1) One-line verdict (max 20 words)
2) 5–10 bullet insights (actionable, concrete)
3) "Next jobs" as JSON array with 3–8 items (each item must include: type, title, instructions)
4) "Risks/unknowns" bullet list (only real uncertainties)
5) End with "DONE"

IMPORTANT:
- Do NOT pretend you executed external actions unless the job explicitly includes evidence.
- If info is missing, propose next jobs to fetch/verify it.
- Keep it practical. No fluff.
SOURCE FILE: {job_path}
"""


def extract_next_jobs(text: str) -> Optional[list]:
    """
    Best-effort parse of the 'Next jobs' JSON array inside the model output.
    Looks for the first '[' ... ']' block that parses to a list.
    """
    # crude but effective: find a bracketed JSON list
    start = text.find("[")
    while start != -1:
        end = text.find("]", start)
        if end == -1:
            break
        candidate = text[start : end + 1].strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        start = text.find("[", start + 1)
    return None


def normalize_next_job(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    t = item.get("type") or item.get("job_type") or "general_insight"
    title = item.get("title") or "Next job"
    instr = item.get("instructions") or item.get("instruction") or item.get("prompt") or "Do the task."
    if not isinstance(t, str) or not isinstance(title, str) or not isinstance(instr, str):
        return None
    return {
        "type": t.strip() or "general_insight",
        "title": title.strip() or "Next job",
        "instructions": instr.strip() or "Do the task.",
        "created_at": dt.datetime.utcnow().isoformat() + "Z",
        "origin": "outbox_worker",
    }


def main() -> int:
    in_dir = os.environ.get("IDA_OUTBOX_DIR", "agent_outbox")
    out_dir = os.environ.get("IDA_RESULTS_DIR", "agent_results")
    done_dir = os.environ.get("IDA_DONE_DIR", "agent_outbox_done")
    ops_log = os.environ.get("IDA_OPS_LOG", os.path.join("ops", "logs", "outbox_worker.log"))

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_KEY") or ""

    safe_mkdir(in_dir)
    safe_mkdir(out_dir)
    safe_mkdir(done_dir)
    safe_mkdir(os.path.dirname(ops_log))

    job_files = sorted(glob.glob(os.path.join(in_dir, "*.json")))
    if not job_files:
        append_text(ops_log, f"{utc_now_compact()} | no_jobs\n")
        print("No jobs found.")
        return 0

    processed = 0
    failed = 0

    for path in job_files:
        basename = os.path.basename(path)
        try:
            job = read_json(path)
        except Exception as e:
            failed += 1
            append_text(ops_log, f"{utc_now_compact()} | bad_json | {basename} | {repr(e)}\n")
            continue

        job_type = pick_job_type(job)
        title = pick_job_title(job)
        instr = pick_job_instructions(job)

        job_id = job.get("id")
        if not isinstance(job_id, str) or not job_id.strip():
            job_id = sha1_short(basename + json.dumps(job, ensure_ascii=False))

        ts = utc_now_compact()
        result_base = f"{ts}_{job_type}_{job_id}".replace("/", "_").replace("\\", "_").replace(" ", "_")

        md_path = os.path.join(out_dir, f"{result_base}.md")
        meta_path = os.path.join(out_dir, f"{result_base}.meta.json")

        prompt = build_prompt(job, path)

        if not api_key:
            # hard fail: we want real work. Without key we still write a result showing missing config.
            ok = False
            answer = "Missing OPENAI_API_KEY. Add the secret and map it into the workflow env.\n\nDONE"
        else:
            ok, answer = openai_chat_completion(prompt=prompt, model=model, api_key=api_key, timeout_s=90)

        meta: Dict[str, Any] = {
            "job_id": job_id,
            "job_type": job_type,
            "title": title,
            "instructions": instr,
            "source_job_file": path,
            "ran_at_utc": dt.datetime.utcnow().isoformat() + "Z",
            "openai_model": model,
            "openai_ok": ok,
        }

        # Next jobs (optional)
        next_jobs = extract_next_jobs(answer) if isinstance(answer, str) else None
        if next_jobs:
            normalized = []
            for item in next_jobs:
                nj = normalize_next_job(item)
                if nj:
                    normalized.append(nj)
            if normalized:
                meta["next_jobs"] = normalized

        # Write outputs
        header = f"# IDA Result\n\n- **Job:** {title}\n- **Type:** {job_type}\n- **ID:** {job_id}\n- **Time (UTC):** {meta['ran_at_utc']}\n- **Model:** {model}\n- **OpenAI OK:** {ok}\n\n---\n\n"
        write_text(md_path, header + (answer or ""))
        write_json(meta_path, meta)

        # Move job to done
        done_path = os.path.join(done_dir, basename)
        try:
            shutil.move(path, done_path)
        except Exception:
            # if move fails, copy+remove
            try:
                shutil.copy2(path, done_path)
                os.remove(path)
            except Exception as e:
                append_text(ops_log, f"{utc_now_compact()} | move_failed | {basename} | {repr(e)}\n")

        processed += 1
        append_text(
            ops_log,
            f"{utc_now_compact()} | processed | {basename} | job_id={job_id} | type={job_type} | openai_ok={ok}\n",
        )

        # tiny pause to avoid rate spikes if many jobs
        time.sleep(0.2)

    print(f"Processed: {processed}, Failed: {failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
