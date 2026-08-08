from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import execution_gateway


class ExecutionGatewayTests(unittest.TestCase):
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

    def _body(self, **changes) -> bytes:
        envelope = {
            "execution_id": 7,
            "approval_id": 3,
            "action_type": "external_outreach",
            "payload": {"recipient": "buyer@example.com"},
            "idempotency_key": "idem-123",
        }
        envelope.update(changes)
        return json.dumps(
            envelope,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def _signature(self, body: bytes) -> str:
        digest = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_accepts_valid_signed_execution_once(self) -> None:
        body = self._body()
        first = execution_gateway.receive_execution(
            body,
            self._signature(body),
            "idem-123",
        )
        second = execution_gateway.receive_execution(
            body,
            self._signature(body),
            "idem-123",
        )

        self.assertTrue(first["accepted"])
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["inbox_id"], second["inbox_id"])
        self.assertEqual(len(execution_gateway.list_inbox()), 1)

    def test_rejects_tampered_body(self) -> None:
        original = self._body()
        tampered = self._body(payload={"recipient": "attacker@example.com"})

        with self.assertRaisesRegex(ValueError, "invalid_signature"):
            execution_gateway.receive_execution(
                tampered,
                self._signature(original),
                "idem-123",
            )

    def test_rejects_action_outside_allowlist(self) -> None:
        body = self._body(action_type="spend_money")

        with self.assertRaisesRegex(ValueError, "action_type_not_allowed"):
            execution_gateway.receive_execution(
                body,
                self._signature(body),
                "idem-123",
            )

    def test_rejects_idempotency_key_reused_for_different_body(self) -> None:
        first = self._body()
        execution_gateway.receive_execution(
            first,
            self._signature(first),
            "idem-123",
        )
        changed = self._body(payload={"recipient": "different@example.com"})

        with self.assertRaisesRegex(ValueError, "idempotency_conflict"):
            execution_gateway.receive_execution(
                changed,
                self._signature(changed),
                "idem-123",
            )


if __name__ == "__main__":
    unittest.main()
