from __future__ import annotations

import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from datetime import datetime
from pathlib import Path

from scripts import (
    clawbar_collect,
    clawbar_commands,
    clawbar_gateway,
    clawbar_metadata,
    clawbar_snapshot,
    clawbar_target_state,
)
from scripts.clawbar_commands import CollectionDeadlineExceeded, CommandOutputExceeded, SubprocessCommandSurface
from tests.collector_fixture import CollectorFixture
from tests.fake_commands import (
    LOCAL_GATEWAY_URL,
    FakeCommandSurface,
    echo_dialed_url,
    failed,
    gateway_ok,
    gateway_unresolved,
    node_hosting,
    node_not_hosting,
    ok,
    text,
)

NODE_HOST_URL = "wss://node-gateway.example.test:18789/openclaw-gw"
CONFIGURED_REMOTE_URL = "wss://configured-gateway.example.test:18789"
ALPHA_URL = "ws://gateway-alpha.example.ts.net:18789"
TAILSCALE_ALPHA = {
    "Peer": {
        "nodekey:PRIVATE-A": {
            "ID": "PRIVATE-A",
            "HostName": "gateway-alpha",
            "DNSName": "gateway-alpha.example.ts.net.",
            "Online": True,
        }
    }
}


def setup_required(tailscale_status: dict[str, object] | None = None) -> FakeCommandSurface:
    """No local Gateway, no node host; Tailscale answers ``tailscale_status`` when given."""
    answers = {"gateway_status": gateway_unresolved(), "node_status": node_not_hosting()}
    if tailscale_status is not None:
        answers["tailscale_status"] = ok(tailscale_status)
    return FakeCommandSurface(**answers)


def node_host_gateway(**answers) -> FakeCommandSurface:
    """The local ``gateway status`` fails, the device hosts a Gateway, and dialing it succeeds."""
    return FakeCommandSurface.healthy(
        gateway_status=[failed(9, "connection broken", "invalid token"), echo_dialed_url()],
        node_status=node_hosting(),
        **answers,
    )


class CollectionTests(CollectorFixture, unittest.TestCase):
    """collect_gateway through its interface, with answers scripted on the Gateway Command Surface."""

    @property
    def state_directory(self) -> Path:
        return self.snapshot_path.parent

    # ---- Gateway status decoding ----

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
        result = self.collect(FakeCommandSurface.healthy(gateway_status=text("{not-json")))

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.MALFORMED_JSON)
        self.assertEqual(self.read_snapshot()["failureKind"], "malformed_json")

    def test_misleading_text_never_overrides_structured_status_or_exit_code(self) -> None:
        healthy = self.collect(
            FakeCommandSurface.healthy(
                gateway_status=ok({"rpc": {"ok": True, "url": LOCAL_GATEWAY_URL}}, stderr="invalid token and connection broken"),
            )
        )
        failed_result = self.collect(FakeCommandSurface.lost(stdout="connection broken"))

        self.assertEqual(healthy.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(failed_result.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED)
        serialized = json.dumps(failed_result.snapshot)
        self.assertNotIn("invalid token", serialized)
        self.assertNotIn("connection broken", serialized)

    def test_initial_failure_without_last_success_is_not_unstable(self) -> None:
        result = self.collect(FakeCommandSurface.lost())

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(self.read_snapshot()["gateway"], {"state": "no_data"})

    def test_reachable_unsupported_json_is_configuration_error(self) -> None:
        result = self.collect(FakeCommandSurface.healthy(gateway_status=ok({"rpc": {"ok": True}})))

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.UNSUPPORTED_JSON)
        self.assertEqual(self.read_snapshot()["gateway"], {"state": "configuration_error"})

    def test_success_timestamps_follow_gateway_validation(self) -> None:
        started_at = time.time()

        def slow_gateway(url: str | None = None) -> subprocess.CompletedProcess[str]:
            time.sleep(0.2)
            return gateway_ok()

        result = self.collect(FakeCommandSurface.healthy(gateway_status=slow_gateway))

        generated_at = datetime.fromisoformat(result.snapshot["generatedAt"].replace("Z", "+00:00")).timestamp()
        self.assertGreaterEqual(generated_at, started_at + 0.15)
        self.assertEqual(result.snapshot["lastSuccessAt"], result.snapshot["generatedAt"])

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

        result = self.collect(FakeCommandSurface.healthy(gateway_status=text("invalid")))

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.MALFORMED_JSON)
        snapshot = self.read_snapshot()
        self.assertEqual(snapshot["lastSuccessAt"], original["lastSuccessAt"])
        self.assertEqual(snapshot["resolutionSource"], "node_host")
        self.assertNotEqual(self.snapshot_path.stat().st_ino, original_inode)
        self.assertEqual(list(self.snapshot_path.parent.glob("snapshot.json.*.tmp")), [])

    def test_misleading_success_stderr_and_nonzero_streams_are_ignored(self) -> None:
        healthy = self.collect(
            FakeCommandSurface.healthy(gateway_status=ok({"rpc": {"ok": True, "url": LOCAL_GATEWAY_URL}}, stderr="invalid token and connection broken"))
        )
        failed_result = self.collect(
            FakeCommandSurface.lost(stdout="connection broken"),
            snapshot_path=self.root / "failed-state" / "snapshot.json",
        )

        self.assertEqual(healthy.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(healthy.snapshot["gateway"], {"state": "healthy"})
        self.assertEqual(failed_result.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(failed_result.snapshot["gateway"], {"state": "no_data"})
        serialized = json.dumps(failed_result.snapshot)
        self.assertNotIn("invalid token", serialized)
        self.assertNotIn("connection broken", serialized)

    # ---- Deadline and metadata failures ----

    def test_deadline_is_shared_across_node_resolution_and_gateway_probe(self) -> None:
        commands = FakeCommandSurface(
            gateway_status=[failed(9, "connection broken", "invalid token"), CollectionDeadlineExceeded()],
            node_status=node_hosting(),
        )

        result = self.collect(commands, deadline=0.10)

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.COMMAND_TIMEOUT)
        self.assertEqual(self.read_snapshot()["failureKind"], "timeout")
        self.assertEqual(commands.questions(), ["gateway_status", "node_status", "gateway_status"])
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
        result = self.collect(FakeCommandSurface.healthy(agents_list=CommandOutputExceeded()))

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(result.snapshot["fleet"], {"available": True, "nodes": []})
        self.assertTrue(result.snapshot["automations"]["available"])
        self.assertEqual(
            result.snapshot["agents"],
            {"available": False, "items": [], "reason": "output_exceeded_limit"},
        )

    def test_oversize_task_surface_marks_agents_section_reason(self) -> None:
        result = self.collect(FakeCommandSurface.healthy(tasks_list=CommandOutputExceeded()))

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(result.snapshot["fleet"], {"available": True, "nodes": []})
        self.assertEqual(
            result.snapshot["agents"],
            {"available": False, "items": [], "reason": "output_exceeded_limit"},
        )

    def test_oversize_nodes_surface_marks_fleet_section_reason(self) -> None:
        result = self.collect(FakeCommandSurface.healthy(nodes_status=CommandOutputExceeded()))

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "degraded"})
        self.assertTrue(result.snapshot["automations"]["available"])
        self.assertEqual(
            result.snapshot["fleet"],
            {"available": False, "nodes": [], "reason": "output_exceeded_limit"},
        )


if __name__ == "__main__":
    unittest.main()
