from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "snapshots.json"


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


if __name__ == "__main__":
    unittest.main()
