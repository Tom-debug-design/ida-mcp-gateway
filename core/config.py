import os

def env(key: str, default: str | None = None) -> str | None:
    v = os.getenv(key)
    if v is None or v.strip() == "":
        return default
    return v.strip()

# --- OpenAI ---
OPENAI_API_KEY = env("OPENAI_API_KEY")
OPENAI_MODEL = env("OPENAI_MODEL", "gpt-4.1-mini")  # trygt og billig-ish default

# --- Runtime controls ---
# 60 min trygt. Bytt til 5 når stabilt.
JOB_GENERATE_INTERVAL_MIN = int(env("JOB_GENERATE_INTERVAL_MIN", "60"))
MAX_JOBS_PER_RUN = int(env("MAX_JOBS_PER_RUN", "1"))  # ALLTID 1 i SAFE MODE

# --- Paths ---
OUTBOX_DIR = env("OUTBOX_DIR", "agent_outbox")
RESULTS_DIR = env("RESULTS_DIR", "agent_results")
OPS_LOG_DIR = env("OPS_LOG_DIR", "ops/logs")
OPS_NEEDS_DIR = env("OPS_NEEDS_DIR", "ops/needs")
OPS_PROPOSALS_DIR = env("OPS_PROPOSALS_DIR", "ops/proposals")
