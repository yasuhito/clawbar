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


    def test_resolves_local_configured_remote_and_node_host_gateways(self) -> None:
        scenarios = {
            "local": FakeCommandSurface.healthy(),
            "configured_remote": FakeCommandSurface.healthy(url=CONFIGURED_REMOTE_URL),
            "node_host": node_host_gateway(),
        }
        for scenario, commands in scenarios.items():
            with self.subTest(scenario=scenario):
                result = self.collect(commands, snapshot_path=self.root / scenario / "snapshot.json")

                self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
                self.assertEqual(result.snapshot["resolutionSource"], scenario)
                self.assertEqual(result.snapshot["gateway"], {"state": "healthy"})
                probes = commands.asked("gateway_status")
                self.assertIsNone(probes[0]["url"])
                if scenario == "node_host":
                    self.assertEqual(commands.questions()[:3], ["gateway_status", "node_status", "gateway_status"])
                    self.assertEqual(probes[1]["url"], NODE_HOST_URL)
                    self.assertNotIn("node-gateway.example.test", json.dumps(result.snapshot))
                    metadata = commands.questions()[3:]
                else:
                    metadata = commands.questions()[1:]
                self.assertEqual(metadata, ["nodes_status", "agents_list", "tasks_list", "cron_list"])
                self.assertEqual(
                    commands.asked("cron_list")[0]["params"],
                    {"includeDisabled": True, "limit": 200, "offset": 0},
                )

    def test_never_persists_a_gateway_url_with_credentials(self) -> None:
        private_url = "wss://operator:PRIVATE-TOKEN@gateway.example.test:18789"

        result = self.collect(FakeCommandSurface.healthy(gateway_status=gateway_ok(private_url)))

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

        self.assertEqual(failed_result.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(failed_result.snapshot["gateway"], {"state": "unstable"})
        self.assertEqual(failed_result.snapshot["resolutionSource"], "node_host")
        self.assertEqual(commands.asked("tailscale_status"), [])

    def test_a_selected_candidate_skips_automatic_resolution(self) -> None:
        candidate_key = "candidate:test"
        self.state_directory.mkdir(parents=True)
        clawbar_gateway.candidate_state_path(self.snapshot_path).write_text(
            json.dumps({
                "schemaVersion": clawbar_gateway.CANDIDATE_STATE_SCHEMA_VERSION,
                "candidates": {candidate_key: {"url": ALPHA_URL}},
            }),
            encoding="utf-8",
        )
        commands = FakeCommandSurface.healthy(gateway_status=echo_dialed_url())

        result = self.collect(commands, candidate_key=candidate_key)

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["resolutionSource"], "tailscale")
        self.assertEqual(commands.asked("gateway_status"), [{"url": ALPHA_URL}])
        self.assertNotIn("node_status", commands.questions())

    def test_a_verified_fallback_is_dialed_once_when_automatic_resolution_is_missing(self) -> None:
        self.state_directory.mkdir(parents=True)
        (self.state_directory / "gateway-verified-target.json").write_text(
            json.dumps({
                "schemaVersion": clawbar_target_state.VERIFIED_TARGET_SCHEMA_VERSION,
                "source": "tailscale",
                "url": ALPHA_URL,
            }),
            encoding="utf-8",
        )
        commands = FakeCommandSurface.healthy(
            gateway_status=[gateway_unresolved(), echo_dialed_url()],
            node_status=node_not_hosting(),
        )

        result = self.collect(commands)

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "healthy"})
        self.assertEqual(result.snapshot["resolutionSource"], "tailscale")
        self.assertEqual(commands.asked("gateway_status"), [{"url": None}, {"url": ALPHA_URL}])
        self.assertEqual(commands.asked("tailscale_status"), [])

    # ---- Gateway Setup Required and Tailscale candidates ----

    def test_lists_tailscale_candidates_only_when_gateway_setup_is_required(self) -> None:
        tailscale_status = {
            "Self": {"ID": "PRIVATE-SELF", "HostName": "local-device", "Online": True},
            "Peer": {
                "nodekey:PRIVATE-A": {
                    "ID": "PRIVATE-A",
                    "HostName": "gateway-alpha",
                    "DNSName": "gateway-alpha.example.ts.net.",
                    "TailscaleIPs": ["100.64.0.10"],
                    "Online": True,
                },
                "nodekey:PRIVATE-B": {
                    "ID": "PRIVATE-B",
                    "HostName": "offline-device",
                    "DNSName": "offline-device.example.ts.net.",
                    "TailscaleIPs": ["100.64.0.11"],
                    "Online": False,
                },
            },
        }
        commands = setup_required(tailscale_status)

        result = self.collect(commands)

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        snapshot = result.snapshot
        self.assertEqual(snapshot["gateway"], {"state": "setup_required"})
        self.assertEqual(snapshot["resolutionSource"], "unresolved")
        candidates = snapshot["setup"]["candidates"]
        self.assertEqual([candidate["name"] for candidate in candidates], ["gateway-alpha"])
        self.assertRegex(candidates[0]["key"], r"^candidate:[0-9a-f]{20}$")
        self.assertEqual(
            snapshot["setup"]["guidance"],
            "Choose a Tailscale device to verify as your OpenClaw Gateway.",
        )
        self.assertEqual(
            snapshot["bar"],
            {"kind": "none", "count": 0, "severity": "warning"},
        )
        serialized = json.dumps(snapshot)
        self.assertNotIn("PRIVATE-", serialized)
        self.assertNotIn("gateway-alpha.example.ts.net", serialized)
        self.assertNotIn("100.64.0.10", serialized)
        self.assertEqual(commands.questions()[-1], "tailscale_status")

    def test_tailscale_candidate_keys_survive_reorder_and_distinguish_devices(self) -> None:
        first_status = {
            "Peer": {
                "nodekey:PRIVATE-A": {
                    "ID": "PRIVATE-A",
                    "HostName": "gateway-alpha",
                    "DNSName": "gateway-alpha.example.ts.net.",
                    "Online": True,
                },
                "nodekey:PRIVATE-B": {
                    "ID": "PRIVATE-B",
                    "HostName": "gateway-beta",
                    "DNSName": "gateway-beta.example.ts.net.",
                    "Online": True,
                },
            }
        }
        reordered_status = {
            "Peer": {
                "nodekey:PRIVATE-B": {
                    "ID": "PRIVATE-B",
                    "HostName": "gateway-aardvark",
                    "DNSName": "gateway-beta.example.ts.net.",
                    "Online": True,
                },
                "nodekey:PRIVATE-A": {
                    "ID": "PRIVATE-A",
                    "HostName": "gateway-zulu",
                    "DNSName": "gateway-alpha.example.ts.net.",
                    "Online": True,
                },
            }
        }

        first = self.collect(setup_required(first_status))
        reordered = self.collect(setup_required(reordered_status))

        first_by_name = {
            candidate["name"]: candidate["key"] for candidate in first.snapshot["setup"]["candidates"]
        }
        reordered_by_name = {
            candidate["name"]: candidate["key"] for candidate in reordered.snapshot["setup"]["candidates"]
        }
        self.assertEqual(first_by_name["gateway-alpha"], reordered_by_name["gateway-zulu"])
        self.assertEqual(first_by_name["gateway-beta"], reordered_by_name["gateway-aardvark"])
        self.assertEqual(len(set(first_by_name.values())), 2)
        serialized = json.dumps(first.snapshot) + json.dumps(reordered.snapshot)
        for private_value in ("PRIVATE-A", "PRIVATE-B", "example.ts.net", "100.64."):
            self.assertNotIn(private_value, serialized)
        candidate_state = self.state_directory / "gateway-candidates.json"
        self.assertEqual(candidate_state.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("PRIVATE-", candidate_state.read_text(encoding="utf-8"))
        self.assertNotIn("PRIVATE-", json.dumps(self.read_notifications()))

    def test_secret_failure_preserves_existing_tailscale_candidates(self) -> None:
        setup = self.collect(setup_required(TAILSCALE_ALPHA), secret=None)
        candidate = setup.snapshot["setup"]["candidates"][0]
        secret_path = self.root / "runtime" / "clawbar" / "node-key-secret"
        secret_path.write_bytes(b"invalid")

        unavailable = self.collect(setup_required(TAILSCALE_ALPHA), secret=None)
        verified = self.collect(
            FakeCommandSurface.healthy(gateway_status=echo_dialed_url()),
            candidate_key=candidate["key"],
            secret=None,
        )

        self.assertEqual(unavailable.snapshot["setup"]["candidates"], [candidate])
        self.assertEqual(
            unavailable.snapshot["setup"]["error"],
            "Clawbar cannot derive private Gateway Candidate Keys. Repair its local key secret.",
        )
        self.assertEqual(verified.snapshot["gateway"], {"state": "healthy"})

    def test_gives_actionable_setup_guidance_without_tailscale(self) -> None:
        result = self.collect(setup_required())

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "setup_required"})
        self.assertEqual(
            result.snapshot["setup"],
            {
                "candidates": [],
                "guidance": "Connect Tailscale on this device, then refresh to find Gateway candidates.",
            },
        )
        self.assertEqual(self.read_notifications(), [])

    def test_preserves_dialed_tailscale_fallback_across_automatic_resolution(self) -> None:
        setup_commands = setup_required(TAILSCALE_ALPHA)
        setup = self.collect(setup_commands)
        self.assertEqual(setup.exit_code, clawbar_collect.ExitCode.OK)
        candidate_key = setup.snapshot["setup"]["candidates"][0]["key"]

        legacy_current_target_path = self.state_directory / "gateway-target.json"
        legacy_current_target_path.write_text('{"url":"ws://legacy.example.test"}', encoding="utf-8")

        verifier = FakeCommandSurface.healthy(gateway_status=echo_dialed_url(LOCAL_GATEWAY_URL))
        verified = self.collect(verifier, candidate_key=candidate_key)
        self.assertEqual(verified.exit_code, clawbar_collect.ExitCode.OK)
        verified_target_path = self.state_directory / "gateway-verified-target.json"
        verified_target = verified_target_path.read_bytes()
        self.assertEqual(json.loads(verified_target)["url"], ALPHA_URL)
        self.assertEqual(verified_target_path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(legacy_current_target_path.exists())

        automatic_commands = FakeCommandSurface.healthy(url=CONFIGURED_REMOTE_URL)
        automatic = self.collect(automatic_commands)
        self.assertEqual(automatic.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(verified_target_path.read_bytes(), verified_target)
        reuser = FakeCommandSurface.healthy(
            gateway_status=[gateway_unresolved(), echo_dialed_url()],
            node_status=node_not_hosting(),
        )
        reused = self.collect(reuser)
        failer = FakeCommandSurface(
            gateway_status=[gateway_unresolved(), failed(9)],
            node_status=node_not_hosting(),
        )
        failed_result = self.collect(failer)

        self.assertEqual(reused.exit_code, clawbar_collect.ExitCode.OK)
        for result in (verified, reused):
            self.assertEqual(result.snapshot["gateway"], {"state": "healthy"})
            self.assertEqual(result.snapshot["resolutionSource"], "tailscale")
            self.assertNotIn("example.ts.net", json.dumps(result.snapshot))
        self.assertEqual(failed_result.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(failed_result.snapshot["gateway"], {"state": "unstable"})
        self.assertEqual(failed_result.snapshot["resolutionSource"], "tailscale")
        every_commands = (setup_commands, verifier, automatic_commands, reuser, failer)
        self.assertEqual(sum(len(commands.asked("tailscale_status")) for commands in every_commands), 1)
        candidate_probes = [
            probe["url"]
            for commands in every_commands
            for probe in commands.asked("gateway_status")
            if probe["url"] is not None
        ]
        self.assertEqual(candidate_probes, [ALPHA_URL, ALPHA_URL, ALPHA_URL])

    def test_verified_fallback_survives_an_unsafe_reported_gateway_url(self) -> None:
        setup = self.collect(setup_required(TAILSCALE_ALPHA))
        candidate_key = setup.snapshot["setup"]["candidates"][0]["key"]

        verified = self.collect(
            FakeCommandSurface.healthy(
                gateway_status=echo_dialed_url("wss://operator:PRIVATE-TOKEN@gateway.example.test:18789"),
            ),
            candidate_key=candidate_key,
        )

        self.assertEqual(verified.exit_code, clawbar_collect.ExitCode.OK)
        verified_state = json.loads(
            (self.state_directory / "gateway-verified-target.json").read_text(encoding="utf-8")
        )
        self.assertEqual(verified_state["url"], ALPHA_URL)
        self.assertFalse((self.state_directory / "gateway-target.json").exists())
        self.assertNotIn("PRIVATE-TOKEN", json.dumps(verified.snapshot))

    def test_failed_verified_fallback_write_keeps_previous_snapshot_published(self) -> None:
        initial = self.collect(FakeCommandSurface.healthy())
        self.assertEqual(initial.exit_code, clawbar_collect.ExitCode.OK)

        candidate_key = "candidate:test"
        (self.state_directory / "gateway-candidates.json").write_text(
            json.dumps({
                "schemaVersion": clawbar_gateway.CANDIDATE_STATE_SCHEMA_VERSION,
                "candidates": {candidate_key: {"url": "wss://gateway-alpha.example.ts.net:18789"}},
            }),
            encoding="utf-8",
        )
        (self.state_directory / "gateway-verified-target.json").mkdir()

        with self.assertRaises(OSError):
            self.collect(
                FakeCommandSurface.healthy(gateway_status=echo_dialed_url()),
                candidate_key=candidate_key,
            )
        self.assertEqual(self.read_snapshot(), initial.snapshot)

    def test_rejects_unverified_and_unsupported_candidates(self) -> None:
        setup = self.collect(setup_required(TAILSCALE_ALPHA))
        self.assertEqual(setup.exit_code, clawbar_collect.ExitCode.OK)
        candidate_key = setup.snapshot["setup"]["candidates"][0]["key"]

        missing = self.collect(setup_required(), candidate_key="candidate:99")
        unsupported = self.collect(
            FakeCommandSurface(gateway_status=ok({"rpc": {"ok": False}})),
            candidate_key=candidate_key,
        )

        self.assertEqual(missing.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(missing.snapshot["gateway"], {"state": "setup_required"})
        self.assertEqual(unsupported.exit_code, clawbar_collect.ExitCode.UNSUPPORTED_JSON)
        self.assertEqual(unsupported.snapshot["gateway"], {"state": "configuration_error"})
        self.assertEqual(
            unsupported.snapshot["setup"]["error"],
            "The selected device does not provide a supported OpenClaw Gateway.",
        )
        serialized = json.dumps(missing.snapshot) + json.dumps(unsupported.snapshot)
        self.assertNotIn("PRIVATE-", serialized)
        self.assertNotIn("example.ts.net", serialized)

    def test_malformed_candidate_response_retains_previous_resolution_source(self) -> None:
        setup = self.collect(setup_required(TAILSCALE_ALPHA))
        candidate_key = setup.snapshot["setup"]["candidates"][0]["key"]
        verified = self.collect(
            FakeCommandSurface.healthy(gateway_status=echo_dialed_url()),
            candidate_key=candidate_key,
        )

        malformed = self.collect(
            FakeCommandSurface.healthy(gateway_status=text("{not-json")),
            candidate_key=candidate_key,
        )

        self.assertEqual(verified.snapshot["resolutionSource"], "tailscale")
        self.assertEqual(malformed.exit_code, clawbar_collect.ExitCode.MALFORMED_JSON)
        self.assertEqual(malformed.snapshot["gateway"], {"state": "configuration_error"})
        self.assertEqual(malformed.snapshot["resolutionSource"], "tailscale")
        self.assertEqual(malformed.snapshot["failureKind"], "malformed_json")

    def test_keeps_setup_required_when_candidate_verification_fails(self) -> None:
        setup = self.collect(setup_required(TAILSCALE_ALPHA))
        self.assertEqual(setup.exit_code, clawbar_collect.ExitCode.OK)
        candidate = setup.snapshot["setup"]["candidates"][0]

        failed_result = self.collect(
            FakeCommandSurface(gateway_status=failed(9)),
            candidate_key=candidate["key"],
        )

        self.assertEqual(failed_result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(failed_result.snapshot["gateway"], {"state": "setup_required"})
        self.assertEqual(failed_result.snapshot["setup"]["candidates"], [candidate])
        self.assertEqual(
            failed_result.snapshot["setup"]["error"],
            "The selected device could not be verified. Check Tailscale or choose another device.",
        )
        self.assertFalse((self.state_directory / "gateway-target.json").exists())

    def test_times_out_candidate_verification_without_accepting_it(self) -> None:
        setup = self.collect(setup_required(TAILSCALE_ALPHA))
        self.assertEqual(setup.exit_code, clawbar_collect.ExitCode.OK)
        candidate_key = setup.snapshot["setup"]["candidates"][0]["key"]

        timed_out = self.collect(
            FakeCommandSurface(gateway_status=CollectionDeadlineExceeded()),
            candidate_key=candidate_key,
        )

        self.assertEqual(timed_out.exit_code, clawbar_collect.ExitCode.COMMAND_TIMEOUT)
        self.assertEqual(timed_out.snapshot["gateway"], {"state": "setup_required"})
        self.assertEqual(timed_out.snapshot["failureKind"], "timeout")
        self.assertEqual(
            timed_out.snapshot["setup"]["error"],
            "Gateway verification timed out. Check Tailscale and try again.",
        )
        self.assertFalse((self.state_directory / "gateway-target.json").exists())


if __name__ == "__main__":
    unittest.main()
