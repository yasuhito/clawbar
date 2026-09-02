from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import clawbar_collect, clawbar_incidents
from tests.collector_fixture import CollectorFixture
from tests.fake_commands import (
    FakeCommandSurface,
    gateway_unresolved,
    node_not_hosting,
    ok,
    text,
)


class IncidentNotificationTests(CollectorFixture, unittest.TestCase):
    assets_directory = (
        Path(clawbar_incidents.__file__).resolve().parent.parent / "assets"
    )
    incident_icon = str(assets_directory / "clawbar-incident.svg")
    recovered_icon = str(assets_directory / "clawbar-recovered.svg")

    def observe(
        self,
        *,
        nodes: list[dict[str, object]] | None = None,
        automations: list[dict[str, object]] | None = None,
        commands: FakeCommandSurface | None = None,
        **environment: str,
    ) -> clawbar_collect.CollectionResult:
        """One collection from a healthy Gateway reporting ``nodes`` and ``automations``."""
        commands = commands or FakeCommandSurface.healthy(
            nodes_status=ok({"nodes": nodes or []}),
            cron_list=ok({"jobs": automations or []}),
        )
        return self.collect(commands, **environment)

    @staticmethod
    def offline_node(node_id: str, name: str) -> dict[str, object]:
        return {"nodeId": node_id, "displayName": name, "connected": False}

    @staticmethod
    def healthy_node(node_id: str, name: str) -> dict[str, object]:
        return {"nodeId": node_id, "displayName": name, "connected": True}

    @staticmethod
    def automation(
        *,
        automation_id: str = "morning-review",
        name: str = "Morning review",
        enabled: bool = True,
        result: str = "error",
    ) -> dict[str, object]:
        return {
            "id": automation_id,
            "name": name,
            "enabled": enabled,
            "schedule": {"kind": "cron"},
            "state": {
                "lastRunStatus": result,
                "consecutiveErrors": 1 if result == "error" else 0,
            },
        }

    def test_each_incident_kind_starts_an_individual_notification(self) -> None:
        scenarios = (
            (
                "configuration error",
                FakeCommandSurface.healthy(gateway_status=ok({"rpc": {"ok": True}})),
                clawbar_collect.ExitCode.UNSUPPORTED_JSON,
                "Gateway: Configuration Error",
            ),
            (
                "automation failure",
                FakeCommandSurface.healthy(cron_list=ok({"jobs": [self.automation()]})),
                clawbar_collect.ExitCode.OK,
                "Morning review: Automation Failure",
            ),
        )
        for index, (name, commands, expected_exit_code, expected_body) in enumerate(
            scenarios
        ):
            with self.subTest(name=name):
                log_path = self.root / f"notifications-{index}.jsonl"
                result = self.collect(
                    commands,
                    snapshot_path=self.root / f"state-{index}" / "snapshot.json",
                    XDG_RUNTIME_DIR=str(self.root / f"runtime-{index}"),
                    FAKE_NOTIFICATION_LOG=str(log_path),
                )
                self.assertEqual(result.exit_code, expected_exit_code)
                notification = json.loads(log_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    notification,
                    [
                        "--app-name=Clawbar",
                        "--urgency=critical",
                        f"--app-icon={self.incident_icon}",
                        "Incident detected",
                        expected_body,
                    ],
                )

    def test_offline_gateway_starts_after_two_consecutive_failures(self) -> None:
        self.observe()
        self.observe(commands=FakeCommandSurface.lost())
        self.assertEqual(self.read_notifications(), [])

        result = self.observe(commands=FakeCommandSurface.lost())

        self.assertNotEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(self.read_notifications()[-1][-1], "Gateway: Offline")

    def test_non_incident_states_stay_quiet(self) -> None:
        self.observe()
        self.observe(nodes=[self.offline_node("node-1", "studio-ops")])
        self.observe(commands=FakeCommandSurface.lost())
        self.observe(commands=FakeCommandSurface.healthy(nodes_status=text("not-json")))
        self.observe(automations=[self.automation(enabled=False)])
        self.observe(
            commands=FakeCommandSurface.healthy(
                agents_list=ok({"agents": [{"id": "planner"}]}),
                tasks_list=ok(
                    {
                        "tasks": [
                            {
                                "agentId": "planner",
                                "status": "failed",
                                "endedAt": 1_700_000_000_000,
                            }
                        ]
                    }
                ),
            )
        )

        self.assertEqual(self.read_notifications(), [])

    def test_gateway_setup_required_stays_quiet(self) -> None:
        setup_log = self.root / "setup-required-notifications.jsonl"
        result = self.collect(
            FakeCommandSurface(
                gateway_status=gateway_unresolved(), node_status=node_not_hosting()
            ),
            XDG_RUNTIME_DIR=str(self.root / "setup-required-runtime"),
            FAKE_NOTIFICATION_LOG=str(setup_log),
        )
        self.assertEqual(result.snapshot["gateway"], {"state": "setup_required"})
        self.assertFalse(setup_log.exists())

    def test_gateway_setup_required_silently_ends_a_previous_gateway_incident(
        self,
    ) -> None:
        self.observe(
            commands=FakeCommandSurface.healthy(
                gateway_status=ok({"rpc": {"ok": False}})
            )
        )
        self.observe(
            commands=FakeCommandSurface(
                gateway_status=gateway_unresolved(), node_status=node_not_hosting()
            )
        )
        self.observe()

        notifications = self.read_notifications()
        self.assertEqual(len(notifications), 1)
        self.assertIn("Incident detected", notifications[0])

    def test_no_data_does_not_repeat_a_still_current_incident(self) -> None:
        failed = [self.automation()]
        self.observe(automations=failed)
        self.snapshot_path.unlink()
        self.observe(commands=FakeCommandSurface.lost())
        self.observe(automations=failed)

        self.assertEqual(len(self.read_notifications()), 1)

    def test_simultaneous_starts_are_grouped_once(self) -> None:
        result = self.observe(
            nodes=[
                self.offline_node("node-1", "studio-ops"),
                self.offline_node("node-2", "archive-box"),
            ],
            automations=[
                self.automation(),
                self.automation(automation_id="nightly-sync", name="Nightly sync"),
            ],
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(
            self.read_notifications(),
            [
                [
                    "--app-name=Clawbar",
                    "--urgency=critical",
                    f"--app-icon={self.incident_icon}",
                    "2 incidents detected",
                    "Morning review: Automation Failure; Nightly sync: Automation Failure",
                ]
            ],
        )

    def test_offline_node_transitions_stay_quiet(self) -> None:
        offline = [self.offline_node("node-1", "studio-ops")]
        healthy = [self.healthy_node("node-1", "studio-ops")]

        self.observe(nodes=offline)
        self.observe(nodes=offline)
        self.observe(nodes=healthy)
        self.observe(nodes=healthy)

        self.assertEqual(self.read_notifications(), [])

    def test_legacy_node_incident_is_purged_without_recovery(self) -> None:
        previous = {
            "schemaVersion": 1,
            "incidents": {
                "node:legacy": {"label": "studio-ops", "state": "Offline"},
            },
        }
        snapshot = {
            "gateway": {"state": "healthy"},
            "fleet": {
                "available": True,
                "nodes": [
                    {"key": "node:legacy", "name": "studio-ops", "state": "offline"}
                ],
            },
            "automations": {"available": True, "items": []},
        }

        state, starts, recoveries = clawbar_incidents.reconcile_incidents(
            snapshot, previous
        )

        self.assertEqual(state["incidents"], {})
        self.assertEqual(starts, [])
        self.assertEqual(recoveries, [])

    def test_simultaneous_recoveries_are_grouped_once(self) -> None:
        failed = [
            self.automation(),
            self.automation(automation_id="nightly-sync", name="Nightly sync"),
        ]
        recovered = [
            self.automation(result="ok"),
            self.automation(
                automation_id="nightly-sync", name="Nightly sync", result="ok"
            ),
        ]
        self.observe(
            nodes=[
                self.offline_node("node-1", "studio-ops"),
                self.offline_node("node-2", "archive-box"),
            ],
            automations=failed,
        )
        self.observe(
            nodes=[
                self.healthy_node("node-1", "studio-ops"),
                self.healthy_node("node-2", "archive-box"),
            ],
            automations=recovered,
        )

        self.assertEqual(len(self.read_notifications()), 2)
        self.assertEqual(
            self.read_notifications()[1],
            [
                "--app-name=Clawbar",
                "--urgency=normal",
                f"--app-icon={self.recovered_icon}",
                "2 incidents resolved",
                "Morning review: Recovered; Nightly sync: Recovered",
            ],
        )

    def test_notification_icons_are_self_contained_plugin_assets(self) -> None:
        for icon_path, status_color in (
            (Path(self.incident_icon), "#e5484d"),
            (Path(self.recovered_icon), "#2f9e44"),
        ):
            with self.subTest(icon=icon_path.name):
                svg = icon_path.read_text(encoding="utf-8").lower()
                self.assertTrue(icon_path.is_file())
                self.assertIn("<svg", svg)
                self.assertIn(status_color, svg)
                self.assertIn(
                    "m8.2 10 a5.2 5.2 0 1 0 8.2 20.4",
                    svg,
                )
                self.assertIn("m5.6 12.2 c5.2 5.6 10.4 1.4 15.6 2", svg)
                self.assertIn("openclaw's canonical chat working claw", svg)
                self.assertIn('transform="rotate(-10 8.6 11)"', svg)
                self.assertNotIn("href=", svg)

        recovery_arguments = clawbar_incidents.notification_arguments(
            [{"label": "Morning review", "state": "Recovered"}],
            recovered=True,
        )
        self.assertEqual(recovery_arguments[-2], "Incident resolved")
        self.assertEqual(recovery_arguments[2], f"--app-icon={self.recovered_icon}")

    def test_removed_target_ends_monitoring_without_recovery(self) -> None:
        self.observe(automations=[self.automation()])
        self.observe(automations=[])
        self.observe(automations=[self.automation(result="ok")])

        self.assertEqual(len(self.read_notifications()), 1)

    def test_disabling_automation_ends_monitoring_without_recovery(self) -> None:
        self.observe(automations=[self.automation()])
        self.observe(automations=[self.automation(enabled=False)])
        self.observe(automations=[self.automation(enabled=True, result="ok")])

        self.assertEqual(len(self.read_notifications()), 1)

    def test_new_desktop_login_may_notify_current_incident_again(self) -> None:
        failed = [self.automation()]
        self.observe(automations=failed)
        self.observe(automations=failed, XDG_RUNTIME_DIR=str(self.root / "next-login"))

        self.assertEqual(len(self.read_notifications()), 2)

    def test_dispatch_failure_preserves_snapshot_and_transition_state(self) -> None:
        offline = [self.offline_node("node-1", "studio-ops")]
        failed = [self.automation()]
        first = self.observe(
            nodes=offline, automations=failed, FAKE_NOTIFICATION_EXIT="7"
        )
        second = self.observe(nodes=offline, automations=failed)

        self.assertEqual(first.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(second.exit_code, clawbar_collect.ExitCode.OK)
        snapshot = json.loads(self.snapshot_path.read_text())
        self.assertEqual(snapshot["fleet"]["nodes"][0]["state"], "offline")
        self.assertEqual(len(self.read_notifications()), 1)
        temporary_files = list(self.snapshot_path.parent.glob("snapshot.json.*.tmp"))
        self.assertEqual(temporary_files, [])


if __name__ == "__main__":
    unittest.main()
