from __future__ import annotations
import os
from datetime import datetime, timezone

from core.config import OUTBOX_DIR, MAX_JOBS_PER_RUN
from core.io_utils import ensure_dir, write_json, utc_now_iso


def new_job_id() -> str:
    # FIFO sort fungerer fordi timestamp først
    return datetime.now(timezone.utc).strftime("job_%Y%m%d_%H%M%S")


def main() -> None:
    ensure_dir(OUTBOX_DIR)

    # SAFE MODE: generer maks 1 jobb per run
    for _ in range(max(1, MAX_JOBS_PER_RUN)):
        jid = new_job_id()
        path = os.path.join(OUTBOX_DIR, f"{jid}.json")

        job = {
            "job_id": jid,
            "job_type": "production",
            "description": "Lag /agent_results/ en konkret ROI-basert next-batch plan (maks 10 tiltak) for de to repoene vi jobber med: atomicbot-agent og PureBloomWorld-site. Ingen repo-navn-fiksering. Fokus: systemer som gir inntekt og automatisering.",
            "input_files": [],
            "output_files": [],
            "status": "created",
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "owner": "ida",
        }

        # Ikke overskriv hvis det somehow finnes
        if not os.path.exists(path):
            write_json(path, job)
        break


if __name__ == "__main__":
    main()
