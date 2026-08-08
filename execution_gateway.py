from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("IDA2_GATEWAY_DB_PATH", "data/execution_gateway.db"))
REQUIRED_FIELDS = {
    "execution_id",
    "approval_id",
    "action_type",
    "payload",
    "idempotency_key",
}


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id INTEGER NOT NULL,
            approval_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            body_sha256 TEXT NOT NULL,
            status TEXT NOT NULL,
            received_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            result TEXT,
            error_type TEXT
        )
        """
    )
    connection.commit()
    return connection


def _allowed_action_types() -> set[str]:
    configured = os.getenv("IDA2_ALLOWED_ACTION_TYPES", "")
    return {item.strip() for item in configured.split(",") if item.strip()}


def _verify_signature(body: bytes, signature_header: str, secret: str) -> None:
    if not secret:
        raise RuntimeError("execution_gateway_secret_not_configured")
    if not signature_header.startswith("sha256="):
        raise ValueError("invalid_signature_format")
    received = signature_header.removeprefix("sha256=")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received, expected):
        raise ValueError("invalid_signature")


def receive_execution(
    body: bytes,
    signature_header: str,
    idempotency_header: str,
) -> dict[str, Any]:
    secret = os.getenv("IDA2_EXECUTION_GATEWAY_SECRET", "").strip()
    _verify_signature(body, signature_header, secret)

    try:
        envelope = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_json") from exc
    if not isinstance(envelope, dict) or not REQUIRED_FIELDS.issubset(envelope):
        raise ValueError("invalid_execution_envelope")
    if not isinstance(envelope["payload"], dict) or not envelope["payload"]:
        raise ValueError("execution_payload_required")
    if envelope["idempotency_key"] != idempotency_header:
        raise ValueError("idempotency_key_mismatch")

    allowed = _allowed_action_types()
    action_type = str(envelope["action_type"])
    if action_type not in allowed:
        raise ValueError("action_type_not_allowed")

    received_at = datetime.now(UTC).isoformat()
    body_sha256 = hashlib.sha256(body).hexdigest()
    try:
        with _connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO execution_inbox(
                    execution_id, approval_id, action_type, payload,
                    idempotency_key, body_sha256, status, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'accepted', ?)
                """,
                (
                    int(envelope["execution_id"]),
                    int(envelope["approval_id"]),
                    action_type,
                    json.dumps(envelope["payload"], sort_keys=True),
                    idempotency_header,
                    body_sha256,
                    received_at,
                ),
            )
            connection.commit()
            inbox_id = int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT id, body_sha256 FROM execution_inbox
                WHERE idempotency_key = ?
                """,
                (idempotency_header,),
            ).fetchone()
        if row is None or row["body_sha256"] != body_sha256:
            raise ValueError("idempotency_conflict") from None
        return {
            "accepted": True,
            "duplicate": True,
            "inbox_id": int(row["id"]),
            "idempotency_key": idempotency_header,
        }

    return {
        "accepted": True,
        "duplicate": False,
        "inbox_id": inbox_id,
        "idempotency_key": idempotency_header,
    }


def list_inbox(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM execution_inbox ORDER BY id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        result.append(item)
    return result


def claim_next_execution() -> dict[str, Any] | None:
    started_at = datetime.now(UTC).isoformat()
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT * FROM execution_inbox
            WHERE status = 'accepted'
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            connection.commit()
            return None
        cursor = connection.execute(
            """
            UPDATE execution_inbox
            SET status = 'running', started_at = ?
            WHERE id = ? AND status = 'accepted'
            """,
            (started_at, row["id"]),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return None
        connection.commit()
        claimed = connection.execute(
            "SELECT * FROM execution_inbox WHERE id = ?",
            (row["id"],),
        ).fetchone()

    assert claimed is not None
    item = dict(claimed)
    item["payload"] = json.loads(item["payload"])
    return item


def finish_inbox_execution(
    inbox_id: int,
    result: dict[str, Any],
    *,
    success: bool,
    error_type: str | None = None,
) -> dict[str, Any]:
    status = "draft_ready" if success else "failed"
    finished_at = datetime.now(UTC).isoformat()
    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE execution_inbox
            SET status = ?, finished_at = ?, result = ?, error_type = ?
            WHERE id = ? AND status = 'running'
            """,
            (
                status,
                finished_at,
                json.dumps(result, sort_keys=True),
                error_type,
                int(inbox_id),
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("inbox_execution_not_running")
        connection.commit()
        row = connection.execute(
            "SELECT * FROM execution_inbox WHERE id = ?",
            (int(inbox_id),),
        ).fetchone()

    assert row is not None
    item = dict(row)
    item["payload"] = json.loads(item["payload"])
    item["result"] = json.loads(item["result"]) if item["result"] else None
    return item
