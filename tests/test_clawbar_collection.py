from __future__ import annotations

import json
import subprocess
import time
import unittest
from datetime import datetime

from scripts import clawbar_collect
from scripts.clawbar_commands import CollectionDeadlineExceeded, CommandOutputExceeded
from tests.collector_fixture import CollectorFixture
from tests.fake_commands import (
    LOCAL_GATEWAY_URL,
    FakeCommandSurface,
    echo_dialed_url,
    failed,
    gateway_ok,
    node_hosting,
    ok,
    text,
)

NODE_HOST_URL = "wss://node-gateway.example.test:18789/openclaw-gw"
CONFIGURED_REMOTE_URL = "wss://configured-gateway.example.test:18789"


def node_host_gateway(**answers) -> FakeCommandSurface:
    """Resolve the Gateway Target from OpenClaw-owned Node-host state."""
    return FakeCommandSurface.healthy(
        gateway_status=[
            failed(9, "connection broken", "invalid token"),
            echo_dialed_url(),
        ],
        node_status=node_hosting(),
        **answers,
    )


class CollectionTests(CollectorFixture, unittest.TestCase):
    """Decode Gateway responses and enforce the shared collection deadline."""

    @property
    def state_directory(self):
        return self.snapshot_path.parent

    def test_healthy_json_publishes_versioned_sanitized_snapshot(self) -> None:
        status = {
            "rpc": {
                "ok": True,
                "url": LOCAL_GATEWAY_URL,
                "note": "invalid token and connection broken are not state",
            },
            "service": {"configAudit": {"issues": [{"message": "not persisted"}]}},
        }

        result = self.collect(FakeCommandSurface.healthy(gateway_status=ok(status)))

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        snapshot = self.read_snapshot()
        self.assertEqual(snapshot["schemaVersion"], 1)
        self.assertEqual(snapshot["refreshIntervalSeconds"], 30)
        self.assertEqual(snapshot["resolutionSource"], "local")
        self.assertEqual(snapshot["gateway"], {"state": "healthy"})
        self.assertEqual(snapshot["lastSuccessAt"], snapshot["generatedAt"])
        serialized = json.dumps(snapshot)
        self.assertNotIn("invalid token", serialized)
        self.assertNotIn("connection broken", serialized)
        self.assertNotIn("not persisted", serialized)

    def test_malformed_json_has_distinct_exit_code(self) -> None:
        result = self.collect(
            FakeCommandSurface.healthy(gateway_status=text("{not-json"))
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.MALFORMED_JSON)
        self.assertEqual(self.read_snapshot()["failureKind"], "malformed_json")

    def test_misleading_text_never_overrides_structured_status_or_exit_code(
        self,
    ) -> None:
        healthy = self.collect(
            FakeCommandSurface.healthy(
                gateway_status=ok(
                    {"rpc": {"ok": True, "url": LOCAL_GATEWAY_URL}},
                    stderr="invalid token and connection broken",
                ),
            )
        )
        failed_result = self.collect(
            FakeCommandSurface.lost(stdout="connection broken")
        )

        self.assertEqual(healthy.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(
            failed_result.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED
        )
        serialized = json.dumps(failed_result.snapshot)
        self.assertNotIn("invalid token", serialized)
        self.assertNotIn("connection broken", serialized)

    def test_initial_failure_without_last_success_is_not_unstable(self) -> None:
        result = self.collect(FakeCommandSurface.lost())

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(self.read_snapshot()["gateway"], {"state": "no_data"})

    def test_reachable_unsupported_json_is_configuration_error(self) -> None:
        result = self.collect(
            FakeCommandSurface.healthy(gateway_status=ok({"rpc": {"ok": True}}))
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.UNSUPPORTED_JSON)
        self.assertEqual(
            self.read_snapshot()["gateway"], {"state": "configuration_error"}
        )

    def test_success_timestamps_follow_gateway_validation(self) -> None:
        started_at = time.time()

        def slow_gateway(url: str | None = None) -> subprocess.CompletedProcess[str]:
            time.sleep(0.2)
            return gateway_ok()

        result = self.collect(FakeCommandSurface.healthy(gateway_status=slow_gateway))

        generated_at = datetime.fromisoformat(
            result.snapshot["generatedAt"]
        ).timestamp()
        self.assertGreaterEqual(generated_at, started_at + 0.15)
        self.assertEqual(
            result.snapshot["lastSuccessAt"], result.snapshot["generatedAt"]
        )

    def test_atomic_replacement_preserves_last_success_metadata(self) -> None:
        original = {
            "schemaVersion": 1,
            "generatedAt": "2026-08-21T00:00:00Z",
            "refreshIntervalSeconds": 30,
            "resolutionSource": "node_host",
            "gateway": {"state": "healthy"},
            "lastSuccessAt": "2026-08-21T00:00:00Z",
            "consecutiveFailures": 0,
        }
        self.snapshot_path.parent.mkdir(parents=True)
        self.snapshot_path.write_text(json.dumps(original), encoding="utf-8")
        original_inode = self.snapshot_path.stat().st_ino

        result = self.collect(
            FakeCommandSurface.healthy(gateway_status=text("invalid"))
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.MALFORMED_JSON)
        snapshot = self.read_snapshot()
        self.assertEqual(snapshot["lastSuccessAt"], original["lastSuccessAt"])
        self.assertEqual(snapshot["resolutionSource"], "node_host")
        self.assertNotEqual(self.snapshot_path.stat().st_ino, original_inode)
        self.assertEqual(
            list(self.snapshot_path.parent.glob("snapshot.json.*.tmp")), []
        )

    def test_misleading_success_stderr_and_nonzero_streams_are_ignored(self) -> None:
        healthy = self.collect(
            FakeCommandSurface.healthy(
                gateway_status=ok(
                    {"rpc": {"ok": True, "url": LOCAL_GATEWAY_URL}},
                    stderr="invalid token and connection broken",
                )
            )
        )
        failed_result = self.collect(
            FakeCommandSurface.lost(stdout="connection broken"),
            snapshot_path=self.root / "failed-state" / "snapshot.json",
        )

        self.assertEqual(healthy.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(healthy.snapshot["gateway"], {"state": "healthy"})
        self.assertEqual(
            failed_result.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED
        )
        self.assertEqual(failed_result.snapshot["gateway"], {"state": "no_data"})
        serialized = json.dumps(failed_result.snapshot)
        self.assertNotIn("invalid token", serialized)
        self.assertNotIn("connection broken", serialized)

    def test_deadline_is_shared_across_node_resolution_and_gateway_probe(self) -> None:
        commands = FakeCommandSurface(
            gateway_status=[
                failed(9, "connection broken", "invalid token"),
                CollectionDeadlineExceeded(),
            ],
            node_status=node_hosting(),
        )

        result = self.collect(commands, deadline=0.10)

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.COMMAND_TIMEOUT)
        self.assertEqual(self.read_snapshot()["failureKind"], "timeout")
        self.assertEqual(
            commands.questions(), ["gateway_status", "node_status", "gateway_status"]
        )
        self.assertEqual(len(set(commands.deadlines)), 1)

    def test_metadata_timeout_degrades_without_gateway_loss(self) -> None:
        commands = FakeCommandSurface.healthy(
            nodes_status=CollectionDeadlineExceeded(),
            agents_list=CollectionDeadlineExceeded(),
        )

        result = self.collect(commands)

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        snapshot = self.read_snapshot()
        self.assertEqual(snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(snapshot["fleet"], {"available": False, "nodes": []})
        self.assertEqual(snapshot["agents"], {"available": False, "items": []})

    def test_metadata_failure_is_degraded_not_gateway_loss(self) -> None:
        result = self.collect(FakeCommandSurface.healthy(tasks_list=failed(9)))

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(result.snapshot["fleet"], {"available": True, "nodes": []})
        self.assertEqual(result.snapshot["agents"], {"available": False, "items": []})

    def test_oversize_agents_surface_marks_section_reason(self) -> None:
        result = self.collect(
            FakeCommandSurface.healthy(agents_list=CommandOutputExceeded())
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(result.snapshot["fleet"], {"available": True, "nodes": []})
        self.assertTrue(result.snapshot["automations"]["available"])
        self.assertEqual(
            result.snapshot["agents"],
            {"available": False, "items": [], "reason": "output_exceeded_limit"},
        )

    def test_oversize_task_surface_marks_agents_section_reason(self) -> None:
        result = self.collect(
            FakeCommandSurface.healthy(tasks_list=CommandOutputExceeded())
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(result.snapshot["fleet"], {"available": True, "nodes": []})
        self.assertEqual(
            result.snapshot["agents"],
            {"available": False, "items": [], "reason": "output_exceeded_limit"},
        )

    def test_oversize_nodes_surface_marks_fleet_section_reason(self) -> None:
        result = self.collect(
            FakeCommandSurface.healthy(nodes_status=CommandOutputExceeded())
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "degraded"})
        self.assertTrue(result.snapshot["automations"]["available"])
        self.assertEqual(
            result.snapshot["fleet"],
            {"available": False, "nodes": [], "reason": "output_exceeded_limit"},
        )

    def test_resolves_local_configured_remote_and_node_host_gateways(self) -> None:
        scenarios = {
            "local": FakeCommandSurface.healthy(),
            "configured_remote": FakeCommandSurface.healthy(url=CONFIGURED_REMOTE_URL),
            "node_host": node_host_gateway(),
        }
        for scenario, commands in scenarios.items():
            with self.subTest(scenario=scenario):
                result = self.collect(
                    commands, snapshot_path=self.root / scenario / "snapshot.json"
                )

                self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
                self.assertEqual(result.snapshot["resolutionSource"], scenario)
                self.assertEqual(result.snapshot["gateway"], {"state": "healthy"})
                probes = commands.asked("gateway_status")
                self.assertIsNone(probes[0]["url"])
                if scenario == "node_host":
                    self.assertEqual(
                        commands.questions()[:3],
                        ["gateway_status", "node_status", "gateway_status"],
                    )
                    self.assertEqual(probes[1]["url"], NODE_HOST_URL)
                    self.assertNotIn(
                        "node-gateway.example.test", json.dumps(result.snapshot)
                    )
                    metadata = commands.questions()[3:]
                else:
                    metadata = commands.questions()[1:]
                self.assertEqual(
                    metadata, ["nodes_status", "agents_list", "tasks_list", "cron_list"]
                )
                self.assertEqual(
                    commands.asked("cron_list")[0]["params"],
                    {"includeDisabled": True, "limit": 200, "offset": 0},
                )

    def test_never_persists_a_gateway_url_with_credentials(self) -> None:
        private_url = "wss://operator:PRIVATE-TOKEN@gateway.example.test:18789"

        result = self.collect(
            FakeCommandSurface.healthy(gateway_status=gateway_ok(private_url))
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["resolutionSource"], "configured_remote")
        self.assertFalse((self.state_directory / "gateway-target.json").exists())
        self.assertNotIn("PRIVATE-TOKEN", json.dumps(result.snapshot))

    def test_a_failing_resolved_node_host_is_gateway_loss(self) -> None:
        healthy = self.collect(node_host_gateway())
        self.assertEqual(healthy.exit_code, clawbar_collect.ExitCode.OK)
        commands = FakeCommandSurface(
            gateway_status=[failed(9, "connection broken", "invalid token"), failed(9)],
            node_status=node_hosting(),
        )

        failed_result = self.collect(commands)

        self.assertEqual(
            failed_result.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED
        )
        self.assertEqual(failed_result.snapshot["gateway"], {"state": "unstable"})
        self.assertEqual(failed_result.snapshot["resolutionSource"], "node_host")
        self.assertEqual(commands.asked("tailscale_status"), [])
