from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from scripts.clawbar_snapshot import SnapshotBuilder

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "snapshots.json"
NO_DATA_FIXTURE = ROOT / "tests" / "fixtures" / "no-data.json"
FIXED_GENERATED_AT = "2026-08-24T17:44:00.000Z"


class DemoFixtureTests(unittest.TestCase):
    def test_committed_snapshots_match_fixed_clock_demo_output(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "clawbar_demo.py"), "--fixtures"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.stdout, FIXTURES.read_text(encoding="utf-8"))

    def test_no_data_fixture_uses_the_snapshot_builder_contract(self) -> None:
        snapshot = SnapshotBuilder(
            None,
            30,
            clock=lambda: FIXED_GENERATED_AT,
        ).failure("command_failed")

        self.assertEqual(
            json.loads(NO_DATA_FIXTURE.read_text(encoding="utf-8")),
            snapshot,
        )


if __name__ == "__main__":
    unittest.main()
