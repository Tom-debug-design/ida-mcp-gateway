from __future__ import annotations

import hashlib
import json
from typing import Any

from execution_gateway import claim_next_execution, finish_inbox_execution


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing_{field}")
    return value.strip()


def build_delivery_draft(execution: dict[str, Any]) -> dict[str, Any]:
    payload = execution["payload"]
    action_type = execution["action_type"]

    if action_type == "external_outreach":
        artifact = {
            "kind": "email_draft",
            "recipient": _required_text(payload, "recipient"),
            "subject": _required_text(payload, "subject"),
            "body": _required_text(payload, "body"),
        }
    elif action_type == "external_publish":
        artifact = {
            "kind": "publication_draft",
            "target": _required_text(payload, "target"),
            "title": _required_text(payload, "title"),
            "content": _required_text(payload, "content"),
        }
    else:
        raise ValueError("unsupported_action_type")

    canonical = json.dumps(artifact, sort_keys=True, separators=(",", ":"))
    return {
        "delivery_status": "draft_ready",
        "artifact_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "artifact": artifact,
    }


def process_next_execution() -> dict[str, Any]:
    execution = claim_next_execution()
    if execution is None:
        return {"status": "idle"}

    try:
        result = build_delivery_draft(execution)
    except Exception as exc:
        finish_inbox_execution(
            execution["id"],
            {"delivery_status": "rejected"},
            success=False,
            error_type=type(exc).__name__,
        )
        raise

    finished = finish_inbox_execution(execution["id"], result, success=True)
    return {
        "status": finished["status"],
        "inbox_id": finished["id"],
        "result": finished["result"],
    }
