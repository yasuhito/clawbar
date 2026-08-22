from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import clawbar_snapshot, clawbar_target_state


class GatewayTargetStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.snapshot_path = Path(self.temporary_directory.name) / "snapshot.json"
        self.state = clawbar_target_state.GatewayTargetState(self.snapshot_path, schema_version=1)

    def test_automatic_target_does_not_replace_verified_tailscale_fallback(self) -> None:
        fallback_url = "wss://gateway-alpha.example.ts.net:18789"
        automatic_url = "wss://configured.example.test:18789"
        self.state.record_success("first", "tailscale", fallback_url, verified_fallback=True)

        self.state.record_success("second", "configured_remote", automatic_url)

        self.assertEqual(self.state.load_verified_fallback(), fallback_url)
        self.assertEqual(self.state.current_url("second"), automatic_url)
        self.assertIsNone(self.state.current_url("first"))

    def test_state_files_are_private_and_reject_urls_with_credentials(self) -> None:
        self.state.record_success(
            "generated-at",
            "tailscale",
            "wss://gateway-alpha.example.ts.net:18789/openclaw-gw",
            verified_fallback=True,
        )

        for path in (self.state.current_path, self.state.verified_fallback_path):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

        for unsafe_url in (
            "wss://user:secret@gateway.example.test:18789",
            "wss://gateway.example.test:18789?token=secret",
        ):
            with self.subTest(unsafe_url=unsafe_url), self.assertRaises(ValueError):
                self.state.record_success("later", "configured_remote", unsafe_url)
        self.assertEqual(
            self.state.current_url("generated-at"),
            "wss://gateway-alpha.example.ts.net:18789/openclaw-gw",
        )

    def test_failed_state_write_never_publishes_new_current_target(self) -> None:
        real_write = clawbar_snapshot.atomic_write_snapshot

        for failing_write in (1, 2):
            with self.subTest(failing_write=failing_write):
                current_root = Path(self.temporary_directory.name) / str(failing_write)
                state = clawbar_target_state.GatewayTargetState(current_root / "snapshot.json", schema_version=1)
                writes = 0

                def write_or_fail(path: Path, value: dict[str, object]) -> None:
                    nonlocal writes
                    writes += 1
                    if writes == failing_write:
                        raise OSError("state write failed")
                    real_write(path, value)

                with mock.patch.object(clawbar_target_state, "atomic_write_snapshot", side_effect=write_or_fail):
                    with self.assertRaisesRegex(OSError, "state write failed"):
                        state.record_success(
                            "new-snapshot",
                            "tailscale",
                            "wss://gateway-alpha.example.ts.net:18789",
                            verified_fallback=True,
                        )

                self.assertFalse(state.current_path.exists())
                self.assertIsNone(state.current_url("new-snapshot"))


if __name__ == "__main__":
    unittest.main()
