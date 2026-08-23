from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "io.github.yasuhito.clawbar"


DEMO_SCENARIOS = (
    "setup-required",
    "healthy",
    "working-agents",
    "unstable-gateway",
    "offline-gateway",
    "degraded-gateway",
    "configuration-error",
    "automation-failure",
    "stale-snapshot",
    "empty-fleet",
    "grouped-incidents",
    "recovery",
)


class MarketplaceContractTest(unittest.TestCase):
    def test_manifest_declares_widget_and_scheduler_service(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["id"], PLUGIN_ID)
        self.assertEqual(
            manifest["description"],
            "A read-only OpenClaw fleet status view for the Omarchy bar.",
        )
        self.assertEqual(set(manifest["kinds"]), {"bar-widget", "service"})
        self.assertEqual(manifest["entryPoints"]["barWidget"], "Clawbar.qml")
        self.assertEqual(manifest["entryPoints"]["service"], "ClawbarService.qml")
        self.assertEqual(manifest["barWidget"]["defaultSection"], "right")
        for entry_point in manifest["entryPoints"].values():
            self.assertTrue((ROOT / entry_point).is_file())
        self.assertTrue((ROOT / "LICENSE").is_file())

    def test_bar_icon_keeps_color_only_signal(self) -> None:
        widget = (ROOT / "Clawbar.qml").read_text(encoding="utf-8")

        self.assertIn("color: root.barSignalColor", widget)
        self.assertIn("width: Style.bar.iconCanvas * 0.875", widget)
        self.assertNotIn("String(root.barCount)", widget)
        self.assertIn("root.warningColor", widget)
        self.assertIn("healthy: root.healthyColor", widget)
        self.assertIn("warning: root.warningColor", widget)

    def test_demo_publishes_all_twelve_sanitized_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            empty_path = root / "bin"
            empty_path.mkdir()
            environment = os.environ.copy()
            environment.update(
                {
                    "CLAWBAR_DEMO_NO_RESCAN": "1",
                    "PATH": str(empty_path),
                    "XDG_RUNTIME_DIR": str(root / "runtime"),
                    "XDG_STATE_HOME": str(root / "state"),
                }
            )
            listed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "clawbar_demo.py"), "--list-scenarios"],
                cwd=ROOT,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(tuple(listed.stdout.splitlines()), DEMO_SCENARIOS)
            self.assertEqual(len(DEMO_SCENARIOS), 12)
            snapshots = {}
            for scenario in DEMO_SCENARIOS:
                with self.subTest(scenario=scenario):
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(ROOT / "scripts" / "clawbar_demo.py"),
                            scenario,
                            "--snapshot",
                            str(root / f"{scenario}.json"),
                        ],
                        cwd=ROOT,
                        env=environment,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    snapshot = json.loads(completed.stdout)
                    self.assertEqual(snapshot["demoScenario"], scenario)
                    snapshots[scenario] = snapshot
                    serialized = json.dumps(snapshot)
                    for prohibited in (
                        "hostname",
                        "account",
                        "destination",
                        "token",
                        "message",
                        "rawError",
                        "/home/",
                    ):
                        self.assertNotIn(prohibited, serialized)
            healthy = dict(snapshots["healthy"])
            working = dict(snapshots["working-agents"])
            healthy.pop("demoScenario")
            working.pop("demoScenario")
            self.assertNotEqual(healthy, working)


    def test_demo_reproduces_grouped_incidents_and_recovery_without_private_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bin_directory = root / "bin"
            bin_directory.mkdir()
            notification_log = root / "notifications.jsonl"
            notify_send = bin_directory / "notify-send"
            notify_send.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "with open(os.environ['NOTIFICATION_LOG'], 'a', encoding='utf-8') as output:\n"
                "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n",
                encoding="utf-8",
            )
            notify_send.chmod(0o755)
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{bin_directory}:{environment['PATH']}",
                    "CLAWBAR_DEMO_NO_RESCAN": "1",
                    "XDG_RUNTIME_DIR": str(root / "runtime"),
                    "XDG_STATE_HOME": str(root / "state"),
                    "NOTIFICATION_LOG": str(notification_log),
                }
            )

            for scenario in ("healthy", "grouped-incidents", "recovery"):
                completed = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "clawbar_demo.py"), scenario],
                    cwd=ROOT,
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                snapshot = json.loads(completed.stdout)
                self.assertEqual(snapshot["demoScenario"], scenario)

            self.assertTrue((root / "runtime" / "clawbar" / "demo-active").is_file())
            self.assertFalse((root / "runtime" / "clawbar" / "incidents.json").exists())
            demo_incidents = root / "runtime" / "clawbar-demo" / "clawbar" / "incidents.json"
            self.assertTrue(demo_incidents.is_file())
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "clawbar_collect.py")],
                cwd=ROOT,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            preserved = json.loads((root / "state" / "clawbar" / "snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(preserved["demoScenario"], "recovery")

            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "clawbar_demo.py"), "--resume"],
                cwd=ROOT,
                env=environment,
                check=True,
            )
            self.assertEqual(
                (root / "runtime" / "clawbar" / "demo-active").read_text(encoding="utf-8"),
                "0\n",
            )
            self.assertFalse(demo_incidents.exists())

            notifications = [
                json.loads(line)
                for line in notification_log.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(notifications), 2)
            self.assertIn("3 Incidents started", notifications[0][2])
            self.assertIn("3 Incidents recovered", notifications[1][2])

            serialized = (root / "state" / "clawbar" / "snapshot.json").read_text(encoding="utf-8")
            for prohibited in (
                "hostname",
                "account",
                "destination",
                "token",
                "message",
                "rawError",
                "/home/",
            ):
                self.assertNotIn(prohibited, serialized)

    def test_submission_draft_matches_marketplace_issue_form(self) -> None:
        title = (ROOT / "MARKETPLACE_SUBMISSION_TITLE.txt").read_text(encoding="utf-8")
        body = (ROOT / "MARKETPLACE_SUBMISSION.md").read_text(encoding="utf-8")
        headings = [
            "### Repository URL",
            "### Category",
            "### Tags",
            "### Suggest a missing tag",
            "### Maintainer notes",
            "### Submission checklist",
        ]
        checklist = [
            "- [x] The repository is public and contains installation and removal instructions.",
            "- [x] I have documented the plugin license and any external dependencies.",
            "- [x] I confirm that I own or have permission to submit this plugin and its preview assets.",
            "- [x] The plugin does not overwrite user configuration without explicit consent.",
            "- [x] I understand that approval is for listing and is not a security review.",
        ]

        self.assertEqual(title, "[Plugin]: Clawbar\n")
        self.assertEqual(
            [line for line in body.splitlines() if line.startswith("### ")],
            headings,
        )
        self.assertIn("\nhttps://github.com/yasuhito/clawbar\n", body)
        self.assertIn("\nWidgets\n", body)
        self.assertIn("\nai, bar, quickshell\n", body)
        self.assertEqual(
            [line for line in body.splitlines() if line.startswith("- [x]")],
            checklist,
        )

    def test_repository_excludes_generated_and_systemd_artifacts(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        tracked_paths = {
            Path(path.decode("utf-8"))
            for path in tracked
            if path
        }

        for path in tracked_paths:
            with self.subTest(path=path):
                self.assertNotIn(".playwright-cli", path.parts)
                self.assertNotIn("__pycache__", path.parts)
                self.assertNotIn(path.suffix, {".pyc", ".pyo", ".pyd"})
                self.assertNotIn(path.suffix, {".service", ".timer"})


if __name__ == "__main__":
    unittest.main()
