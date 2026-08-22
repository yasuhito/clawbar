from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.collector_fixture import CollectorFixture


class IncidentNotificationTests(CollectorFixture, unittest.TestCase):
    def collect(
        self,
        *,
        nodes: list[dict[str, object]] | None = None,
        automations: list[dict[str, object]] | None = None,
        extra: dict[str, str] | None = None,
    ):
        environment = {
            "FAKE_NODES": json.dumps({"nodes": nodes or []}),
            "FAKE_AUTOMATIONS": json.dumps({"jobs": automations or []}),
            **(extra or {}),
        }
        return self.run_external("local", environment_overrides=environment)

    @staticmethod
    def offline_node(node_id: str, name: str) -> dict[str, object]:
        return {"nodeId": node_id, "displayName": name, "connected": False}

    @staticmethod
    def healthy_node(node_id: str, name: str) -> dict[str, object]:
        return {"nodeId": node_id, "displayName": name, "connected": True}

    @staticmethod
    def automation(*, enabled: bool = True, result: str = "error") -> dict[str, object]:
        return {
            "id": "morning-review",
            "name": "Morning review",
            "enabled": enabled,
            "schedule": {"kind": "cron"},
            "state": {"lastRunStatus": result, "consecutiveErrors": 1 if result == "error" else 0},
        }

    def test_each_incident_kind_starts_an_individual_notification(self) -> None:
        scenarios = (
            (
                "configuration error",
                {"FAKE_STDOUT": json.dumps({"rpc": {"ok": True}})},
                23,
                "Gateway: Configuration Error",
            ),
            (
                "offline node",
                {"FAKE_NODES": json.dumps({"nodes": [self.offline_node("node-1", "studio-ops")]})},
                0,
                "studio-ops: Offline",
            ),
            (
                "automation failure",
                {"FAKE_AUTOMATIONS": json.dumps({"jobs": [self.automation()]})},
                0,
                "Morning review: Automation Failure",
            ),
        )
        for index, (name, overrides, expected_exit_code, expected_body) in enumerate(scenarios):
            with self.subTest(name=name):
                log_path = self.root / f"notifications-{index}.jsonl"
                result = self.run_external(
                    "local",
                    environment_overrides={
                        "XDG_RUNTIME_DIR": str(self.root / f"runtime-{index}"),
                        "XDG_STATE_HOME": str(self.root / f"state-{index}"),
                        "FAKE_NOTIFICATION_LOG": str(log_path),
                        **overrides,
                    },
                )
                self.assertEqual(result.returncode, expected_exit_code)
                notification = json.loads(log_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    notification,
                    [
                        "--app-name=Clawbar",
                        "--urgency=critical",
                        "Clawbar: Incident started",
                        expected_body,
                    ],
                )

    def test_offline_gateway_starts_after_two_consecutive_failures(self) -> None:
        self.collect()
        self.collect(extra={"FAKE_EXIT": "9", "FAKE_STDOUT": "connection broken"})
        self.assertEqual(self.read_notifications(), [])

        result = self.collect(extra={"FAKE_EXIT": "9", "FAKE_STDOUT": "connection broken"})

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.read_notifications()[-1][-1], "Gateway: Offline")

    def test_non_incident_states_stay_quiet(self) -> None:
        self.collect()
        self.collect(extra={"FAKE_EXIT": "9", "FAKE_STDOUT": "connection broken"})
        self.collect(extra={"FAKE_NODES": "not-json"})
        self.collect(automations=[self.automation(enabled=False)])
        self.collect(
            extra={
                "FAKE_AGENTS": json.dumps({"agents": [{"id": "planner"}]}),
                "FAKE_TASKS": json.dumps(
                    {"tasks": [{"agentId": "planner", "status": "failed", "endedAt": 1_700_000_000_000}]}
                ),
            }
        )

        self.assertEqual(self.read_notifications(), [])

    def test_gateway_setup_required_stays_quiet(self) -> None:
        setup_log = self.root / "setup-required-notifications.jsonl"
        self.run_external(
            "local",
            environment_overrides={
                "XDG_RUNTIME_DIR": str(self.root / "setup-required-runtime"),
                "XDG_STATE_HOME": str(self.root / "setup-required-state"),
                "FAKE_NOTIFICATION_LOG": str(setup_log),
                "FAKE_EXIT": "9",
                "FAKE_STDOUT": "connection broken",
            },
        )
        self.assertFalse(setup_log.exists())
    def test_gateway_setup_required_silently_ends_a_previous_gateway_incident(self) -> None:
        self.run_external(
            "local",
            environment_overrides={"FAKE_STDOUT": json.dumps({"rpc": {"ok": False}})},
        )
        self.run_external("unresolved")
        self.run_external("local")

        notifications = self.read_notifications()
        self.assertEqual(len(notifications), 1)
        self.assertIn("Clawbar: Incident started", notifications[0])


    def test_no_data_does_not_repeat_a_still_current_incident(self) -> None:
        offline = [self.offline_node("node-1", "studio-ops")]
        self.collect(nodes=offline)
        (self.root / "external-state" / "clawbar" / "snapshot.json").unlink()
        self.collect(extra={"FAKE_EXIT": "9", "FAKE_STDOUT": "connection broken"})
        self.collect(nodes=offline)

        self.assertEqual(len(self.read_notifications()), 1)

    def test_simultaneous_starts_are_grouped_once(self) -> None:
        result = self.collect(
            nodes=[self.offline_node("node-1", "studio-ops"), self.offline_node("node-2", "archive-box")],
            automations=[self.automation()],
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            self.read_notifications(),
            [[
                "--app-name=Clawbar",
                "--urgency=critical",
                "Clawbar: 3 Incidents started",
                "studio-ops: Offline; archive-box: Offline; Morning review: Automation Failure",
            ]],
        )

    def test_repeated_failed_and_recovered_states_do_not_repeat(self) -> None:
        offline = [self.offline_node("node-1", "studio-ops")]
        healthy = [self.healthy_node("node-1", "studio-ops")]

        self.collect(nodes=offline)
        self.collect(nodes=offline)
        self.collect(nodes=healthy)
        self.collect(nodes=healthy)

        self.assertEqual(
            self.read_notifications(),
            [
                [
                    "--app-name=Clawbar",
                    "--urgency=critical",
                    "Clawbar: Incident started",
                    "studio-ops: Offline",
                ],
                [
                    "--app-name=Clawbar",
                    "--urgency=normal",
                    "Clawbar: Incident recovered",
                    "studio-ops: Recovered",
                ],
            ],
        )

    def test_simultaneous_recoveries_are_grouped_once(self) -> None:
        self.collect(
            nodes=[self.offline_node("node-1", "studio-ops"), self.offline_node("node-2", "archive-box")],
            automations=[self.automation()],
        )
        self.collect(
            nodes=[self.healthy_node("node-1", "studio-ops"), self.healthy_node("node-2", "archive-box")],
            automations=[self.automation(result="ok")],
        )

        self.assertEqual(len(self.read_notifications()), 2)
        self.assertEqual(
            self.read_notifications()[1],
            [
                "--app-name=Clawbar",
                "--urgency=normal",
                "Clawbar: 3 Incidents recovered",
                "studio-ops: Recovered; archive-box: Recovered; Morning review: Recovered",
            ],
        )

    def test_removed_target_ends_monitoring_without_recovery(self) -> None:
        self.collect(nodes=[self.offline_node("node-1", "studio-ops")])
        self.collect(nodes=[])
        self.collect(nodes=[self.healthy_node("node-1", "studio-ops")])

        self.assertEqual(len(self.read_notifications()), 1)

    def test_disabling_automation_ends_monitoring_without_recovery(self) -> None:
        self.collect(automations=[self.automation()])
        self.collect(automations=[self.automation(enabled=False)])
        self.collect(automations=[self.automation(enabled=True, result="ok")])

        self.assertEqual(len(self.read_notifications()), 1)

    def test_new_desktop_login_may_notify_current_incident_again(self) -> None:
        offline = [self.offline_node("node-1", "studio-ops")]
        self.collect(nodes=offline)
        self.collect(
            nodes=offline,
            extra={"XDG_RUNTIME_DIR": str(self.root / "next-login")},
        )

        self.assertEqual(len(self.read_notifications()), 2)

    def test_dispatch_failure_preserves_snapshot_and_transition_state(self) -> None:
        offline = [self.offline_node("node-1", "studio-ops")]
        first = self.collect(nodes=offline, extra={"FAKE_NOTIFICATION_EXIT": "7"})
        second = self.collect(nodes=offline)

        self.assertEqual(first.returncode, 0)
        self.assertEqual(second.returncode, 0)
        snapshot = json.loads((self.root / "external-state" / "clawbar" / "snapshot.json").read_text())
        self.assertEqual(snapshot["fleet"]["nodes"][0]["state"], "offline")
        self.assertEqual(len(self.read_notifications()), 1)
        temporary_files = list(Path(self.root / "external-state" / "clawbar").glob("snapshot.json.*.tmp"))
        self.assertEqual(temporary_files, [])


if __name__ == "__main__":
    unittest.main()
