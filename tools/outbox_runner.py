import os
import json
import time
import datetime
import hashlib
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]

OUTBOX_DIR = ROOT / "agent_outbox"
DONE_DIR = ROOT / "agent_outbox_done"
RESULTS_DIR = ROOT / "agent_results"
OPS_DIR = ROOT / "ops"
LOGS_DIR = OPS_DIR / "logs"
NEEDS_DIR = OPS_DIR / "needs"

ALLOWED_DOMAINS_FILE = OPS_DIR / "allowed_domains.txt"

MAX_JOBS_PER_RUN = int(os.getenv("MAX_JOBS_PER_RUN", "5"))
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()

FETCH_TIMEOUT_SECONDS = int(os.getenv("FETCH_TIMEOUT_SECONDS", "25"))
FETCH_MAX_BYTES = int(os.getenv("FETCH_MAX_BYTES", "1500000"))
USER_AGENT = os.getenv("USER_AGENT", "IDA-MCP-Gateway/1.0")

SERPER_ENDPOINT = "https://google.serper.dev/search"

def ensure_dirs():
    for d in [OUTBOX_DIR, DONE_DIR, RESULTS_DIR, LOGS_DIR, NEEDS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def load_allowed_domains():
    if not ALLOWED_DOMAINS_FILE.exists():
        # safe default: no domains allowed
        return set()
    domains = set()
    for line in ALLOWED_DOMAINS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        domains.add(line.lower())
    return domains

def is_domain_allowed(url: str, allowed_domains: set) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if not host:
            return False, ""
        # allow exact match or subdomain of listed domain
        for d in allowed_domains:
            if host == d or host.endswith("." + d):
                return True, host
        return False, host
    except Exception:
        return False, ""

def now_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def append_ops_log(lines: list[str]):
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    log_path = LOGS_DIR / f"{date_str}.md"
    header = f"# IDA ops log {date_str}\n\n" if not log_path.exists() else ""
    with log_path.open("a", encoding="utf-8") as f:
        if header:
            f.write(header)
        for ln in lines:
            f.write(ln.rstrip() + "\n")
        f.write("\n")

def read_job(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def list_jobs_fifo() -> list[Path]:
    if not OUTBOX_DIR.exists():
        return []
    jobs = [p for p in OUTBOX_DIR.glob("*.json") if p.is_file()]
    # FIFO: oldest mtime first, then name
    jobs.sort(key=lambda p: (p.stat().st_mtime, p.name))
    return jobs

def move_to_done(job_path: Path, status: str):
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    done_name = f"{job_path.stem}.{status}.{ts}.json"
    dest = DONE_DIR / done_name
    dest.write_text(job_path.read_text(encoding="utf-8"), encoding="utf-8")
    job_path.unlink(missing_ok=True)

def mark_need(job_id: str, reason: str, details: dict | None = None):
    payload = {
        "job_id": job_id,
        "status": "NEEDS_INPUT",
        "reason": reason,
        "details": details or {},
        "timestamp": now_iso()
    }
    write_json(NEEDS_DIR / f"{job_id}_needs.json", payload)

def serper_search(query: str, num_results: int = 10, recency_days: int | None = None) -> dict:
    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY missing")

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"q": query}
    # Serper supports different params, but keep minimal and robust.
    # recency_days not guaranteed across all modes; we store it as metadata.
    resp = requests.post(SERPER_ENDPOINT, headers=headers, json=payload, timeout=25)
    resp.raise_for_status()
    data = resp.json()

    # Normalize top results (organic)
    organic = data.get("organic", []) or []
    trimmed = organic[: max(1, min(num_results, 20))]
    normalized = []
    for r in trimmed:
        normalized.append({
            "title": r.get("title"),
            "link": r.get("link"),
            "snippet": r.get("snippet"),
            "position": r.get("position"),
        })

    return {
        "query": query,
        "requested_num_results": num_results,
        "recency_days": recency_days,
        "results": normalized,
        "raw": data,
        "timestamp": now_iso(),
    }

def fetch_url_text(url: str) -> dict:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT_SECONDS, stream=True)
    status_code = resp.status_code

    # Read limited bytes
    content = b""
    for chunk in resp.iter_content(chunk_size=65536):
        if not chunk:
            break
        content += chunk
        if len(content) > FETCH_MAX_BYTES:
            break

    content_type = resp.headers.get("Content-Type", "")
    # Try decode
    encoding = resp.encoding or "utf-8"
    try:
        html = content.decode(encoding, errors="replace")
    except Exception:
        html = content.decode("utf-8", errors="replace")

    text = ""
    if "html" in content_type.lower() or "<html" in html.lower():
        soup = BeautifulSoup(html, "lxml")
        # Remove obvious junk
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
    else:
        # plain text or other
        text = html.strip()

    return {
        "url": url,
        "status_code": status_code,
        "content_type": content_type,
        "bytes_read": len(content),
        "fetched_at": now_iso(),
        "text": text,
    }

def handle_web_search(job: dict):
    job_id = job.get("job_id") or sha1(json.dumps(job, sort_keys=True))
    query = job.get("query", "").strip()
    num_results = int(job.get("num_results", 10))
    recency_days = job.get("recency_days", None)

    if not query:
        mark_need(job_id, "Missing query", {"expected": "job.query"})
        return job_id, "FAILED"

    res = serper_search(query=query, num_results=num_results, recency_days=recency_days)
    out_path = RESULTS_DIR / f"{job_id}_search.json"
    write_json(out_path, res)

    append_ops_log([
        f"## WEB_SEARCH",
        f"- job_id: `{job_id}`",
        f"- query: `{query}`",
        f"- results: {len(res['results'])}",
        f"- output: `{out_path.as_posix()}`",
        f"- status: OK",
    ])

    return job_id, "OK"

def handle_fetch_url(job: dict, allowed_domains: set):
    job_id = job.get("job_id") or sha1(json.dumps(job, sort_keys=True))
    url = job.get("url", "").strip()

    if not url:
        mark_need(job_id, "Missing url", {"expected": "job.url"})
        return job_id, "FAILED"

    allowed, host = is_domain_allowed(url, allowed_domains)
    if not allowed:
        mark_need(job_id, "Domain not allowed", {"url": url, "host": host, "hint": "Add domain to ops/allowed_domains.txt"})
        append_ops_log([
            f"## FETCH_URL",
            f"- job_id: `{job_id}`",
            f"- url: `{url}`",
            f"- host: `{host}`",
            f"- status: BLOCKED (domain not allowed)",
        ])
        return job_id, "BLOCKED"

    fetched = fetch_url_text(url)
    text_out = RESULTS_DIR / f"{job_id}_content.txt"
    meta_out = RESULTS_DIR / f"{job_id}_meta.json"

    write_text(text_out, fetched["text"])
    meta = {k: fetched[k] for k in ["url", "status_code", "content_type", "bytes_read", "fetched_at"]}
    write_json(meta_out, meta)

    append_ops_log([
        f"## FETCH_URL",
        f"- job_id: `{job_id}`",
        f"- url: `{url}`",
        f"- host: `{host}`",
        f"- http: {fetched['status_code']}",
        f"- bytes: {fetched['bytes_read']}",
        f"- output_text: `{text_out.as_posix()}`",
        f"- output_meta: `{meta_out.as_posix()}`",
        f"- status: OK",
    ])

    return job_id, "OK"

def main():
    ensure_dirs()
    allowed_domains = load_allowed_domains()

    jobs = list_jobs_fifo()
    if not jobs:
        append_ops_log([f"## RUN", f"- {now_iso()} no jobs in outbox"])
        return

    processed = 0
    for job_path in jobs[:MAX_JOBS_PER_RUN]:
        try:
            job = read_job(job_path)
            job_type = (job.get("type") or "").strip().upper()

            if job_type == "WEB_SEARCH":
                job_id, status = handle_web_search(job)
            elif job_type == "FETCH_URL":
                job_id, status = handle_fetch_url(job, allowed_domains)
            else:
                job_id = job.get("job_id") or job_path.stem
                mark_need(job_id, "Unknown job type", {"type": job.get("type"), "supported": ["WEB_SEARCH", "FETCH_URL"]})
                append_ops_log([
                    f"## UNKNOWN_JOB",
                    f"- job_id: `{job_id}`",
                    f"- file: `{job_path.as_posix()}`",
                    f"- type: `{job.get('type')}`",
                    f"- status: FAILED",
                ])
                status = "FAILED"

            move_to_done(job_path, status)
            processed += 1

            # be nice to rate limits
            time.sleep(1.0)

        except Exception as e:
            # never crash the whole run because of one job
            job_id = job_path.stem
            mark_need(job_id, "Runner exception", {"error": str(e), "file": job_path.name})
            append_ops_log([
                f"## ERROR",
                f"- job_id: `{job_id}`",
                f"- file: `{job_path.as_posix()}`",
                f"- error: `{str(e)}`",
                f"- status: FAILED (job skipped, runner continues)",
            ])
            move_to_done(job_path, "FAILED")
            continue

    append_ops_log([
        f"## RUN_SUMMARY",
        f"- timestamp: {now_iso()}",
        f"- processed: {processed}",
        f"- max_per_run: {MAX_JOBS_PER_RUN}",
    ])

if __name__ == "__main__":
    main()
