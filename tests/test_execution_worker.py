from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import execution_gateway
from execution_worker import build_delivery_draft, process_next_execution


class ExecutionWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "gateway.db"
        self.db_patch = patch.object(execution_gateway, "DB_PATH", self.database)
        self.db_patch.start()
        self.env_patch = patch.dict(
            "os.environ",
            {
                "IDA2_EXECUTION_GATEWAY_SECRET": "test-secret",
                "IDA2_ALLOWED_ACTION_TYPES": "external_outreach,external_publish",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def _enqueue(self, payload: dict[str, str]) -> None:
        envelope = {
            "execution_id": 11,
            "approval_id": 8,
            "action_type": "external_outreach",
            "payload": payload,
            "idempotency_key": "worker-idem-1",
        }
        body = json.dumps(
            envelope,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        execution_gateway.receive_execution(
            body,
            f"sha256={digest}",
            "worker-idem-1",
        )

    def test_worker_builds_draft_once(self) -> None:
        self._enqueue(
            {
                "recipient": "buyer@example.com",
                "subject": "Paid audit pilot",
                "body": "Would you like to review a scoped paid pilot?",
            }
        )

        result = process_next_execution()
        idle = process_next_execution()

        self.assertEqual(result["status"], "draft_ready")
        self.assertEqual(result["result"]["artifact"]["kind"], "email_draft")
        self.assertEqual(len(result["result"]["artifact_id"]), 64)
        self.assertEqual(idle, {"status": "idle"})

    def test_worker_rejects_incomplete_outreach_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing_body"):
            build_delivery_draft(
                {
                    "action_type": "external_outreach",
                    "payload": {
                        "recipient": "buyer@example.com",
                        "subject": "Missing body",
                    },
                }
            )

    def test_claim_is_atomic_and_cannot_repeat(self) -> None:
        self._enqueue(
            {
                "recipient": "buyer@example.com",
                "subject": "Pilot",
                "body": "Test",
            }
        )

        claimed = execution_gateway.claim_next_execution()
        second = execution_gateway.claim_next_execution()

        self.assertEqual(claimed["status"], "running")
        self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()
