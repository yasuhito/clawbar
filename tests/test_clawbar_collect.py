from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock
from datetime import datetime
from pathlib import Path

from scripts import clawbar_collect, clawbar_metadata
from tests.collector_fixture import CollectorFixture

class MetadataTests(unittest.TestCase):
    def test_secret_created_by_another_collector_is_validated(self) -> None:
        with (
            mock.patch.object(Path, "read_bytes", side_effect=[FileNotFoundError, b""]),
            mock.patch.object(os, "open", side_effect=FileExistsError),
        ):
            with self.assertRaisesRegex(OSError, "Invalid Clawbar local key secret"):
                clawbar_metadata.load_local_key_secret()


class CollectorCommandTests(CollectorFixture, unittest.TestCase):
    def test_healthy_json_publishes_versioned_sanitized_snapshot(self) -> None:
        status = {
            "rpc": {
                "ok": True,
                "url": "ws://127.0.0.1:18789",
                "note": "invalid token and connection broken are not state",
            },
            "service": {"configAudit": {"issues": [{"message": "not persisted"}]}},
        }

        result = self.run_collector(stdout=json.dumps(status))

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
        result = self.run_collector(stdout="{not-json")

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.MALFORMED_JSON)
        self.assertEqual(self.read_snapshot()["failureKind"], "malformed_json")

    def test_misleading_text_never_overrides_structured_status_or_exit_code(self) -> None:
        status = json.dumps({"rpc": {"ok": True, "url": "ws://127.0.0.1:18789"}})

        healthy = self.run_collector(
            stdout=status,
            stderr="invalid token and connection broken",
        )
        failed = self.run_collector(
            stdout="connection broken",
            stderr="invalid token",
            exit_code=9,
        )

        self.assertEqual(healthy.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(failed.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED)
        serialized = json.dumps(failed.snapshot)
        self.assertNotIn("invalid token", serialized)
        self.assertNotIn("connection broken", serialized)

    def test_initial_failure_without_last_success_is_not_unstable(self) -> None:
        result = self.run_collector(stdout="connection broken", stderr="invalid token", exit_code=9)

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(self.read_snapshot()["gateway"], {"state": "no_data"})

    def test_reachable_unsupported_json_is_configuration_error(self) -> None:
        result = self.run_collector(stdout=json.dumps({"rpc": {"ok": True}}))

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.UNSUPPORTED_JSON)
        self.assertEqual(self.read_snapshot()["gateway"], {"state": "configuration_error"})

    def test_success_timestamps_follow_gateway_validation(self) -> None:
        started_at = time.time()

        result = self.run_collector(gateway_delay=0.2)

        generated_at = datetime.fromisoformat(result.snapshot["generatedAt"].replace("Z", "+00:00")).timestamp()
        self.assertGreaterEqual(generated_at, started_at + 0.15)
        self.assertEqual(result.snapshot["lastSuccessAt"], result.snapshot["generatedAt"])

    def test_deadline_is_shared_across_node_resolution_and_gateway_probe(self) -> None:
        started_at = time.monotonic()

        result = self.run_collector(
            node_delay=0.03,
            gateway_delay=0.04,
            deadline=0.10,
            scenario="node_host",
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.COMMAND_TIMEOUT)
        self.assertLess(time.monotonic() - started_at, 0.25)
        self.assertEqual(self.read_snapshot()["failureKind"], "timeout")

    def test_metadata_timeout_degrades_without_gateway_loss(self) -> None:
        result = self.run_collector(nodes_delay=0.3, deadline=0.1)

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        snapshot = self.read_snapshot()
        self.assertEqual(snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(snapshot["fleet"], {"available": False, "nodes": []})
        self.assertEqual(snapshot["agents"], {"available": False, "items": []})

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

        result = self.run_collector(stdout="invalid")

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.MALFORMED_JSON)
        snapshot = self.read_snapshot()
        self.assertEqual(snapshot["lastSuccessAt"], original["lastSuccessAt"])
        self.assertEqual(snapshot["resolutionSource"], "node_host")
        self.assertNotEqual(self.snapshot_path.stat().st_ino, original_inode)
        self.assertEqual(list(self.snapshot_path.parent.glob("snapshot.json.*.tmp")), [])


class ExternalCollectorTests(CollectorFixture, unittest.TestCase):

    def test_executable_resolves_local_configured_remote_and_node_host_gateways(self) -> None:
        expected_sources = {
            "local": "local",
            "configured_remote": "configured_remote",
            "node_host": "node_host",
        }
        for scenario, expected_source in expected_sources.items():
            with self.subTest(scenario=scenario):
                self.call_log_path.unlink(missing_ok=True)
                result = self.run_external(scenario)

                self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
                snapshot = json.loads(result.stdout)
                self.assertEqual(snapshot["resolutionSource"], expected_source)
                self.assertEqual(snapshot["gateway"], {"state": "healthy"})
                calls = self.read_calls()
                self.assertEqual(calls[0][:2], ["gateway", "status"])
                metadata_offset = 1
                if scenario == "node_host":
                    self.assertNotIn("--url", calls[0])
                    self.assertEqual(calls[1], ["node", "status", "--json"])
                    self.assertEqual(calls[2][:2], ["gateway", "status"])
                    url_index = calls[2].index("--url") + 1
                    self.assertEqual(
                        calls[2][url_index],
                        "wss://node-gateway.example.test:18789/openclaw-gw",
                    )
                    self.assertNotIn("node-gateway.example.test", result.stdout)
                    metadata_offset = 3
                else:
                    self.assertNotIn("--url", calls[0])
                self.assertEqual(calls[metadata_offset][:3], ["nodes", "status", "--json"])
                self.assertEqual(calls[metadata_offset + 1][:3], ["gateway", "call", "agents.list"])
                self.assertEqual(calls[metadata_offset + 2][:3], ["gateway", "call", "tasks.list"])
                self.assertEqual(calls[metadata_offset + 3][:3], ["gateway", "call", "cron.list"])
                cron_call = calls[metadata_offset + 3]
                cron_params = json.loads(cron_call[cron_call.index("--params") + 1])
                self.assertEqual(cron_params, {"includeDisabled": True, "limit": 200, "offset": 0})
                self.assertEqual(len(calls), metadata_offset + 4)

    def test_executable_never_persists_a_gateway_url_with_credentials(self) -> None:
        private_url = "wss://operator:PRIVATE-TOKEN@gateway.example.test:18789"
        result = self.run_external(
            "configured_remote",
            environment_overrides={
                "FAKE_STDOUT": json.dumps({"rpc": {"ok": True, "url": private_url}}),
            },
        )

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
        self.assertFalse(
            (self.root / "external-state" / "clawbar" / "gateway-target.json").exists()
        )
        self.assertNotIn("PRIVATE-TOKEN", result.stdout)

    def test_executable_treats_a_failing_resolved_node_host_as_gateway_loss(self) -> None:
        healthy = self.run_external("node_host")
        self.assertEqual(healthy.returncode, clawbar_collect.ExitCode.OK, healthy.stderr)
        self.call_log_path.unlink(missing_ok=True)

        failed = self.run_external(
            "node_host",
            environment_overrides={"FAKE_EXIT": "9"},
        )

        self.assertEqual(failed.returncode, clawbar_collect.ExitCode.COMMAND_FAILED, failed.stderr)
        snapshot = json.loads(failed.stdout)
        self.assertEqual(snapshot["gateway"], {"state": "unstable"})
        self.assertEqual(snapshot["resolutionSource"], "node_host")
        self.assertNotIn(["tailscale", "status", "--json"], self.read_calls())

    def test_executable_lists_tailscale_candidates_only_when_gateway_setup_is_required(self) -> None:
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

        result = self.run_external(
            "unresolved",
            environment_overrides={"FAKE_TAILSCALE_STATUS": json.dumps(tailscale_status)},
        )

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertEqual(snapshot["gateway"], {"state": "setup_required"})
        self.assertEqual(snapshot["resolutionSource"], "unresolved")
        candidates = snapshot["setup"]["candidates"]
        self.assertEqual([candidate["name"] for candidate in candidates], ["gateway-alpha"])
        candidate_key = candidates[0]["key"]
        self.assertRegex(candidate_key, r"^candidate:[0-9a-f]{20}$")
        self.assertEqual(
            snapshot["setup"]["guidance"],
            "Choose a Tailscale device to verify as your OpenClaw Gateway.",
        )
        self.assertEqual(snapshot["bar"], {"count": 0, "severity": "warning"})
        self.assertNotIn("PRIVATE-", result.stdout)
        self.assertNotIn("gateway-alpha.example.ts.net", result.stdout)
        self.assertNotIn("100.64.0.10", result.stdout)
        self.assertEqual(self.read_calls()[-1], ["tailscale", "status", "--json"])

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

        first = self.run_external(
            "unresolved",
            environment_overrides={"FAKE_TAILSCALE_STATUS": json.dumps(first_status)},
        )
        reordered = self.run_external(
            "unresolved",
            environment_overrides={"FAKE_TAILSCALE_STATUS": json.dumps(reordered_status)},
        )

        first_by_name = {
            candidate["name"]: candidate["key"]
            for candidate in json.loads(first.stdout)["setup"]["candidates"]
        }
        reordered_by_name = {
            candidate["name"]: candidate["key"]
            for candidate in json.loads(reordered.stdout)["setup"]["candidates"]
        }
        self.assertEqual(first_by_name["gateway-alpha"], reordered_by_name["gateway-zulu"])
        self.assertEqual(first_by_name["gateway-beta"], reordered_by_name["gateway-aardvark"])
        self.assertEqual(len(set(first_by_name.values())), 2)
        serialized = first.stdout + reordered.stdout
        for private_value in ("PRIVATE-A", "PRIVATE-B", "example.ts.net", "100.64."):
            self.assertNotIn(private_value, serialized)
        candidate_state = self.root / "external-state" / "clawbar" / "gateway-candidates.json"
        self.assertEqual(candidate_state.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("PRIVATE-", candidate_state.read_text(encoding="utf-8"))
        self.assertNotIn("PRIVATE-", json.dumps(self.read_notifications()))

    def test_secret_failure_preserves_existing_tailscale_candidates(self) -> None:
        tailscale_status = {
            "Peer": {
                "nodekey:PRIVATE-A": {
                    "ID": "PRIVATE-A",
                    "HostName": "gateway-alpha",
                    "DNSName": "gateway-alpha.example.ts.net.",
                    "Online": True,
                }
            }
        }
        environment = {"FAKE_TAILSCALE_STATUS": json.dumps(tailscale_status)}
        setup = self.run_external("unresolved", environment_overrides=environment)
        candidate = json.loads(setup.stdout)["setup"]["candidates"][0]
        secret_path = self.root / "runtime" / "clawbar" / "node-key-secret"
        secret_path.write_bytes(b"invalid")

        unavailable = self.run_external("unresolved", environment_overrides=environment)
        verified = self.run_external(
            "unresolved",
            collector_arguments=["--verify-candidate", candidate["key"]],
        )

        unavailable_snapshot = json.loads(unavailable.stdout)
        self.assertEqual(unavailable_snapshot["setup"]["candidates"], [candidate])
        self.assertEqual(
            unavailable_snapshot["setup"]["error"],
            "Clawbar cannot derive private Gateway Candidate Keys. Repair its local key secret.",
        )
        self.assertEqual(json.loads(verified.stdout)["gateway"], {"state": "healthy"})

    def test_executable_gives_actionable_setup_guidance_without_tailscale(self) -> None:
        result = self.run_external("unresolved")

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertEqual(snapshot["gateway"], {"state": "setup_required"})
        self.assertEqual(
            snapshot["setup"],
            {
                "candidates": [],
                "guidance": "Connect Tailscale on this device, then refresh to find Gateway candidates.",
            },
        )
        self.assertEqual(self.read_notifications(), [])

    def test_executable_preserves_dialed_tailscale_fallback_across_automatic_resolution(self) -> None:
        tailscale_status = {
            "Peer": {
                "nodekey:PRIVATE-A": {
                    "ID": "PRIVATE-A",
                    "HostName": "gateway-alpha",
                    "DNSName": "gateway-alpha.example.ts.net.",
                    "Online": True,
                }
            }
        }
        setup = self.run_external(
            "unresolved",
            environment_overrides={"FAKE_TAILSCALE_STATUS": json.dumps(tailscale_status)},
        )
        self.assertEqual(setup.returncode, clawbar_collect.ExitCode.OK, setup.stderr)
        candidate_key = json.loads(setup.stdout)["setup"]["candidates"][0]["key"]

        verified = self.run_external(
            "unresolved",
            environment_overrides={"FAKE_REPORTED_URL": "ws://127.0.0.1:18789"},
            collector_arguments=["--verify-candidate", candidate_key],
        )
        self.assertEqual(verified.returncode, clawbar_collect.ExitCode.OK, verified.stderr)
        state_directory = self.root / "external-state" / "clawbar"
        verified_target_path = state_directory / "gateway-verified-target.json"
        current_target_path = state_directory / "gateway-target.json"
        verified_target = verified_target_path.read_bytes()
        self.assertEqual(json.loads(verified_target)["url"], "ws://gateway-alpha.example.ts.net:18789")
        self.assertEqual(json.loads(current_target_path.read_bytes())["url"], "ws://127.0.0.1:18789")
        for path in (verified_target_path, current_target_path):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

        automatic = self.run_external("configured_remote")
        self.assertEqual(automatic.returncode, clawbar_collect.ExitCode.OK, automatic.stderr)
        self.assertEqual(verified_target_path.read_bytes(), verified_target)
        reused = self.run_external("unresolved")
        failed = self.run_external(
            "unresolved",
            environment_overrides={"FAKE_CANDIDATE_MODE": "failed"},
        )

        self.assertEqual(reused.returncode, clawbar_collect.ExitCode.OK, reused.stderr)
        for result in (verified, reused):
            snapshot = json.loads(result.stdout)
            self.assertEqual(snapshot["gateway"], {"state": "healthy"})
            self.assertEqual(snapshot["resolutionSource"], "tailscale")
            self.assertNotIn("example.ts.net", result.stdout)
        self.assertEqual(failed.returncode, clawbar_collect.ExitCode.COMMAND_FAILED, failed.stderr)
        failed_snapshot = json.loads(failed.stdout)
        self.assertEqual(failed_snapshot["gateway"], {"state": "unstable"})
        self.assertEqual(failed_snapshot["resolutionSource"], "tailscale")
        calls = self.read_calls()
        self.assertEqual(sum(call == ["tailscale", "status", "--json"] for call in calls), 1)
        candidate_probes = [
            call for call in calls
            if call[:2] == ["gateway", "status"] and "--url" in call
        ]
        self.assertEqual(len(candidate_probes), 3)
        self.assertTrue(all("--require-rpc" in call and "--timeout" in call for call in candidate_probes))

    def test_verified_fallback_survives_an_unsafe_reported_gateway_url(self) -> None:
        tailscale_status = {
            "Peer": {
                "nodekey:PRIVATE-A": {
                    "ID": "PRIVATE-A",
                    "HostName": "gateway-alpha",
                    "DNSName": "gateway-alpha.example.ts.net.",
                    "Online": True,
                }
            }
        }
        setup = self.run_external(
            "unresolved",
            environment_overrides={"FAKE_TAILSCALE_STATUS": json.dumps(tailscale_status)},
        )
        candidate_key = json.loads(setup.stdout)["setup"]["candidates"][0]["key"]

        verified = self.run_external(
            "unresolved",
            environment_overrides={
                "FAKE_REPORTED_URL": "wss://operator:PRIVATE-TOKEN@gateway.example.test:18789",
            },
            collector_arguments=["--verify-candidate", candidate_key],
        )

        self.assertEqual(verified.returncode, clawbar_collect.ExitCode.OK, verified.stderr)
        state_directory = self.root / "external-state" / "clawbar"
        verified_state = json.loads(
            (state_directory / "gateway-verified-target.json").read_text(encoding="utf-8")
        )
        self.assertEqual(verified_state["url"], "ws://gateway-alpha.example.ts.net:18789")
        self.assertFalse((state_directory / "gateway-target.json").exists())
        self.assertNotIn("PRIVATE-TOKEN", verified.stdout)

    def test_failed_verified_fallback_write_keeps_previous_current_target_published(self) -> None:
        automation_id = "stable-automation-id"
        automations = {
            "jobs": [{
                "id": automation_id,
                "name": "Investigate",
                "enabled": True,
                "schedule": {"kind": "cron"},
                "state": {},
            }]
        }
        initial = self.run_external(
            "local",
            environment_overrides={"FAKE_AUTOMATIONS": json.dumps(automations)},
        )
        self.assertEqual(initial.returncode, clawbar_collect.ExitCode.OK, initial.stderr)
        initial_snapshot = json.loads(initial.stdout)

        state_directory = self.root / "external-state" / "clawbar"
        candidate_key = "candidate:test"
        candidate_url = "wss://gateway-alpha.example.ts.net:18789"
        (state_directory / "gateway-candidates.json").write_text(
            json.dumps({
                "schemaVersion": clawbar_collect.SCHEMA_VERSION,
                "candidates": {candidate_key: {"url": candidate_url}},
            }),
            encoding="utf-8",
        )
        (state_directory / "gateway-verified-target.json").mkdir()
        self.call_log_path.unlink(missing_ok=True)

        failed = self.run_external(
            "unresolved",
            collector_arguments=["--verify-candidate", candidate_key],
        )
        self.assertNotEqual(failed.returncode, clawbar_collect.ExitCode.OK)
        snapshot_path = state_directory / "snapshot.json"
        self.assertEqual(json.loads(snapshot_path.read_text(encoding="utf-8")), initial_snapshot)

        history = self.run_external(
            "local",
            collector_arguments=["--automation-history", automation_id],
        )
        self.assertEqual(history.returncode, clawbar_collect.ExitCode.OK, history.stderr)
        history_call = self.read_calls()[-1]
        self.assertEqual(history_call[:2], ["cron", "runs"])
        self.assertNotIn("--url", history_call)

    def test_executable_rejects_unverified_and_unsupported_candidates(self) -> None:
        tailscale_status = {
            "Peer": {
                "nodekey:PRIVATE-A": {
                    "HostName": "gateway-alpha",
                    "ID": "PRIVATE-A",
                    "DNSName": "gateway-alpha.example.ts.net.",
                    "Online": True,
                }
            }
        }
        setup = self.run_external(
            "unresolved",
            environment_overrides={"FAKE_TAILSCALE_STATUS": json.dumps(tailscale_status)},
        )
        self.assertEqual(setup.returncode, clawbar_collect.ExitCode.OK, setup.stderr)
        candidate_key = json.loads(setup.stdout)["setup"]["candidates"][0]["key"]

        missing = self.run_external(
            "unresolved",
            collector_arguments=["--verify-candidate", "candidate:99"],
        )
        unsupported = self.run_external(
            "unresolved",
            environment_overrides={"FAKE_CANDIDATE_MODE": "unsupported"},
            collector_arguments=["--verify-candidate", candidate_key],
        )

        self.assertEqual(missing.returncode, clawbar_collect.ExitCode.OK, missing.stderr)
        self.assertEqual(json.loads(missing.stdout)["gateway"], {"state": "setup_required"})
        self.assertEqual(unsupported.returncode, clawbar_collect.ExitCode.UNSUPPORTED_JSON, unsupported.stderr)
        unsupported_snapshot = json.loads(unsupported.stdout)
        self.assertEqual(unsupported_snapshot["gateway"], {"state": "configuration_error"})
        self.assertEqual(
            unsupported_snapshot["setup"]["error"],
            "The selected device does not provide a supported OpenClaw Gateway.",
        )
        self.assertNotIn("PRIVATE-", missing.stdout + unsupported.stdout)
        self.assertNotIn("example.ts.net", missing.stdout + unsupported.stdout)

    def test_executable_keeps_setup_required_when_candidate_verification_fails(self) -> None:
        tailscale_status = {
            "Peer": {
                "nodekey:PRIVATE-A": {
                    "ID": "PRIVATE-A",
                    "HostName": "gateway-alpha",
                    "DNSName": "gateway-alpha.example.ts.net.",
                    "Online": True,
                }
            }
        }
        setup = self.run_external(
            "unresolved",
            environment_overrides={"FAKE_TAILSCALE_STATUS": json.dumps(tailscale_status)},
        )
        self.assertEqual(setup.returncode, clawbar_collect.ExitCode.OK, setup.stderr)
        candidate = json.loads(setup.stdout)["setup"]["candidates"][0]

        failed = self.run_external(
            "unresolved",
            environment_overrides={"FAKE_CANDIDATE_MODE": "failed"},
            collector_arguments=["--verify-candidate", candidate["key"]],
        )

        self.assertEqual(failed.returncode, clawbar_collect.ExitCode.OK, failed.stderr)
        snapshot = json.loads(failed.stdout)
        self.assertEqual(snapshot["gateway"], {"state": "setup_required"})
        self.assertEqual(snapshot["setup"]["candidates"], [candidate])
        self.assertEqual(
            snapshot["setup"]["error"],
            "The selected device could not be verified. Check Tailscale or choose another device.",
        )
        self.assertFalse((self.root / "external-state" / "clawbar" / "gateway-target.json").exists())

    def test_executable_times_out_candidate_verification_without_accepting_it(self) -> None:
        tailscale_status = {
            "Peer": {
                "nodekey:PRIVATE-A": {
                    "ID": "PRIVATE-A",
                    "HostName": "gateway-alpha",
                    "DNSName": "gateway-alpha.example.ts.net.",
                    "Online": True,
                }
            }
        }
        setup = self.run_external(
            "unresolved",
            environment_overrides={"FAKE_TAILSCALE_STATUS": json.dumps(tailscale_status)},
        )
        self.assertEqual(setup.returncode, clawbar_collect.ExitCode.OK, setup.stderr)
        candidate_key = json.loads(setup.stdout)["setup"]["candidates"][0]["key"]

        started_at = time.monotonic()
        timed_out = self.run_external(
            "unresolved",
            timeout=14,
            environment_overrides={"FAKE_GATEWAY_DELAY": "30"},
            collector_arguments=["--verify-candidate", candidate_key],
        )
        elapsed = time.monotonic() - started_at

        self.assertEqual(timed_out.returncode, clawbar_collect.ExitCode.COMMAND_TIMEOUT, timed_out.stderr)
        snapshot = json.loads(timed_out.stdout)
        self.assertEqual(snapshot["gateway"], {"state": "setup_required"})
        self.assertEqual(snapshot["failureKind"], "timeout")
        self.assertEqual(snapshot["setup"]["error"], "Gateway verification timed out. Check Tailscale and try again.")
        self.assertLess(elapsed, 12.25)
        self.assertFalse((self.root / "external-state" / "clawbar" / "gateway-target.json").exists())


    def test_executable_distinguishes_empty_fleet_from_missing_gateway(self) -> None:
        result = self.run_external("local")

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertEqual(snapshot["gateway"], {"state": "healthy"})
        self.assertEqual(snapshot["fleet"], {"available": True, "nodes": []})
        self.assertEqual(snapshot["agents"], {"available": True, "items": []})

    def test_executable_sanitizes_fleet_activity_and_task_results(self) -> None:
        private_sentinels = [
            "PRIVATE-HOST",
            "PRIVATE-IP",
            "PRIVATE-ACCOUNT",
            "PRIVATE-INSTRUCTION",
            "PRIVATE-DESTINATION",
            "PRIVATE-ERROR",
        ]
        nodes = {
            "nodes": [
                {
                    "displayName": "Local",
                    "connected": True,
                    "platform": "linux",
                    "modelIdentifier": "workstation",
                    "version": "2026.7.1",
                    "lastSeenAtMs": 1_787_280_000_000,
                    "nodeId": "PRIVATE-HOST",
                    "ip": "PRIVATE-IP",
                },
                {"nodeId": "PRIVATE-HOST-2", "displayName": "studio-ops", "connected": True},
            ]
        }
        agents = {
            "agents": [
                {"id": "planner", "model": "gpt-5", "workspace": "PRIVATE-HOST"},
                {"id": "builder", "accountId": "PRIVATE-ACCOUNT"},
                {"id": "observer"},
                {"id": "indexer"},
            ]
        }
        tasks = {
            "tasks": [
                {
                    "agentId": "planner",
                    "status": "running",
                    "updatedAt": 1_787_280_005_000,
                    "title": "PRIVATE-INSTRUCTION",
                },
                {
                    "agentId": "planner",
                    "status": "failed",
                    "endedAt": 1_787_280_004_000,
                    "error": "PRIVATE-ERROR",
                },
                {
                    "agentId": "builder",
                    "status": "queued",
                    "updatedAt": 1_787_280_003_000,
                    "destination": "PRIVATE-DESTINATION",
                },
                {
                    "agentId": "observer",
                    "status": "completed",
                    "endedAt": 1_787_280_002_000,
                },
            ]
        }

        result = self.run_external(
            "local",
            environment_overrides={
                "FAKE_NODES": json.dumps(nodes),
                "FAKE_AGENTS": json.dumps(agents),
                "FAKE_TASKS": json.dumps(tasks),
            },
        )

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertEqual([node["name"] for node in snapshot["fleet"]["nodes"]], ["Local", "studio-ops"])
        node_keys = [node["key"] for node in snapshot["fleet"]["nodes"]]
        self.assertEqual(len(set(node_keys)), 2)
        self.assertTrue(all(key.startswith("node:") for key in node_keys))
        by_name = {agent["name"]: agent for agent in snapshot["agents"]["items"]}
        self.assertEqual(by_name["planner"]["activity"], "working")
        self.assertEqual(by_name["planner"]["taskResult"]["state"], "failed")
        self.assertEqual(by_name["builder"]["activity"], "waiting")
        self.assertEqual(by_name["builder"]["taskResult"], {"state": "none"})
        self.assertEqual(by_name["observer"]["activity"], "idle")
        self.assertEqual(by_name["observer"]["taskResult"]["state"], "succeeded")
        self.assertEqual(by_name["indexer"]["activity"], "idle")
        self.assertEqual(by_name["indexer"]["taskResult"], {"state": "none"})
        self.assertEqual(snapshot["gateway"], {"state": "healthy"})
        for sentinel in private_sentinels:
            self.assertNotIn(sentinel, result.stdout)

    def test_same_named_node_registrations_collapse_to_freshest_connected_node(self) -> None:
        first_nodes = {
            "nodes": [
                {
                    "nodeId": "PRIVATE-NODE-A",
                    "displayName": "MacBook Pro",
                    "connected": True,
                    "lastSeenAtMs": 1_000,
                    "platform": "macOS 26.5.1",
                    "modelIdentifier": "MacBookPro18,3",
                    "version": "2026.1.8",
                },
                {
                    "nodeId": "PRIVATE-NODE-B",
                    "displayName": "MacBook Pro",
                    "connected": True,
                    "lastSeenAtMs": 2_000,
                    "platform": "macos",
                    "version": "2026.7.1",
                },
                {
                    "nodeId": "PRIVATE-NODE-LEGACY",
                    "displayName": "MacBook Pro",
                    "connected": False,
                    "version": "2026.10.0",
                },
                {
                    "nodeId": "PRIVATE-STUDIO-CURRENT",
                    "displayName": "Studio",
                    "connected": True,
                    "lastSeenAtMs": 3_000,
                    "platform": "macOS 27.0",
                },
                {
                    "nodeId": "PRIVATE-STUDIO-LEGACY",
                    "displayName": "Studio",
                    "connected": False,
                    "platform": "macOS 26.5.1",
                },
            ]
        }
        second_nodes = {"nodes": list(reversed(first_nodes["nodes"]))}
        replacement_nodes = {
            "nodes": [
                {
                    "nodeId": "PRIVATE-NODE-C",
                    "displayName": "MacBook Pro",
                    "connected": True,
                    "lastSeenAtMs": 3_000,
                    "version": "replacement",
                }
            ]
        }

        first = self.run_external("local", environment_overrides={"FAKE_NODES": json.dumps(first_nodes)})
        second = self.run_external("local", environment_overrides={"FAKE_NODES": json.dumps(second_nodes)})
        replacement = self.run_external(
            "local",
            environment_overrides={"FAKE_NODES": json.dumps(replacement_nodes)},
        )
        first_fleet = json.loads(first.stdout)["fleet"]["nodes"]
        second_fleet = json.loads(second.stdout)["fleet"]["nodes"]
        replacement_fleet = json.loads(replacement.stdout)["fleet"]["nodes"]

        self.assertEqual(first.returncode, clawbar_collect.ExitCode.OK, first.stderr)
        self.assertEqual(second.returncode, clawbar_collect.ExitCode.OK, second.stderr)
        self.assertEqual(replacement.returncode, clawbar_collect.ExitCode.OK, replacement.stderr)
        self.assertEqual(
            {node["name"]: node for node in first_fleet},
            {node["name"]: node for node in second_fleet},
        )
        self.assertEqual(len(first_fleet), 2)
        self.assertEqual(first_fleet[0]["state"], "healthy")
        self.assertEqual(first_fleet[0]["platform"], "macOS 26.5.1")
        self.assertEqual(first_fleet[0]["model"], "MacBookPro18,3")
        self.assertEqual(first_fleet[0]["version"], "2026.7.1")
        self.assertEqual(replacement_fleet[0]["version"], "replacement")
        self.assertEqual(replacement_fleet[0]["key"], first_fleet[0]["key"])
        self.assertNotIn("PRIVATE-NODE", first.stdout + second.stdout + replacement.stdout)
        studio = next(node for node in first_fleet if node["name"] == "Studio")
        self.assertEqual(studio["platform"], "macOS 27.0")

    def test_fresh_registration_after_first_hundred_duplicates_is_retained(self) -> None:
        nodes = [
            {
                "nodeId": f"PRIVATE-NODE-{index}",
                "displayName": "MacBook Pro",
                "connected": False,
            }
            for index in range(100)
        ]
        nodes.append(
            {
                "nodeId": "PRIVATE-NODE-CURRENT",
                "displayName": "MacBook Pro",
                "connected": True,
                "lastSeenAtMs": 3_000,
                "version": "current",
            }
        )

        result = self.run_external(
            "local",
            environment_overrides={"FAKE_NODES": json.dumps({"nodes": nodes})},
        )
        fleet = json.loads(result.stdout)["fleet"]["nodes"]

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
        self.assertEqual(len(fleet), 1)
        self.assertEqual(fleet[0]["state"], "healthy")
        self.assertEqual(fleet[0]["version"], "current")

    def test_node_keys_stay_stable_without_runtime_directory(self) -> None:
        nodes = {"nodes": [{"nodeId": "PRIVATE-NODE", "displayName": "Local", "connected": True}]}
        environment = {"FAKE_NODES": json.dumps(nodes), "XDG_RUNTIME_DIR": ""}

        first = self.run_external("local", environment_overrides=environment)
        second = self.run_external("local", environment_overrides=environment)

        first_node = json.loads(first.stdout)["fleet"]["nodes"][0]
        second_node = json.loads(second.stdout)["fleet"]["nodes"][0]
        self.assertEqual(first.returncode, clawbar_collect.ExitCode.OK, first.stderr)
        self.assertEqual(second.returncode, clawbar_collect.ExitCode.OK, second.stderr)
        self.assertEqual(first_node["key"], second_node["key"])
        self.assertTrue(first_node["key"].startswith("node:"))
        self.assertNotIn("PRIVATE-NODE", first.stdout + second.stdout)


    def test_invalid_node_key_secret_makes_fleet_unavailable(self) -> None:
        secret_path = self.root / "runtime" / "clawbar" / "node-key-secret"
        secret_path.parent.mkdir(parents=True)
        secret_path.write_bytes(b"invalid")
        nodes = {"nodes": [{"nodeId": "PRIVATE-NODE", "displayName": "Local", "connected": True}]}

        result = self.run_external("local", environment_overrides={"FAKE_NODES": json.dumps(nodes)})

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertEqual(snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(snapshot["fleet"], {"available": False, "nodes": []})
        self.assertNotIn("PRIVATE-NODE", result.stdout)

    def test_node_without_private_identity_makes_fleet_unavailable(self) -> None:
        nodes = {"nodes": [{"displayName": "Local", "connected": True}]}

        result = self.run_external("local", environment_overrides={"FAKE_NODES": json.dumps(nodes)})

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertEqual(snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(snapshot["fleet"], {"available": False, "nodes": []})


    def test_metadata_failure_is_degraded_not_gateway_loss(self) -> None:
        result = self.run_external(
            "local",
            environment_overrides={"FAKE_TASKS_EXIT": "9"},
        )

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertEqual(snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(snapshot["fleet"], {"available": True, "nodes": []})
        self.assertEqual(snapshot["agents"], {"available": False, "items": []})

    def test_executable_ignores_misleading_success_stderr_and_nonzero_streams(self) -> None:
        healthy = self.run_external(
            "local",
            environment_overrides={"FAKE_STDERR": "invalid token and connection broken"},
        )
        failed = self.run_external(
            "local",
            environment_overrides={
                "FAKE_EXIT": "9",
                "FAKE_STDOUT": "connection broken",
                "FAKE_STDERR": "invalid token",
                "XDG_STATE_HOME": str(self.root / "failed-state"),
            },
        )

        self.assertEqual(healthy.returncode, clawbar_collect.ExitCode.OK, healthy.stderr)
        self.assertEqual(json.loads(healthy.stdout)["gateway"], {"state": "healthy"})
        self.assertEqual(failed.returncode, clawbar_collect.ExitCode.COMMAND_FAILED, failed.stderr)
        self.assertEqual(json.loads(failed.stdout)["gateway"], {"state": "no_data"})
        self.assertNotIn("invalid token", failed.stdout)
        self.assertNotIn("connection broken", failed.stdout)

    def test_executable_enforces_default_twelve_second_whole_collection_deadline(self) -> None:
        started_at = time.monotonic()
        with self.fake_environment(FAKE_SCENARIO="node_host", FAKE_NODE_DELAY="30"):
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{self.root}{os.pathsep}{environment['PATH']}",
                    "XDG_STATE_HOME": str(self.root / "deadline-state"),
                    "XDG_RUNTIME_DIR": str(self.root / "deadline-runtime"),
                }
            )
            result = subprocess.run(
                [sys.executable, str(Path(clawbar_collect.__file__))],
                capture_output=True,
                check=False,
                text=True,
                timeout=14,
                env=environment,
            )
        elapsed = time.monotonic() - started_at

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.COMMAND_TIMEOUT, result.stderr)
        self.assertGreaterEqual(elapsed, 10.5)
        self.assertLess(elapsed, 12.25)
        self.assertEqual(json.loads(result.stdout)["failureKind"], "timeout")


class RefreshIntervalTests(unittest.TestCase):
    def test_accepts_bounds_and_default(self) -> None:
        parser = clawbar_collect.build_parser()

        self.assertEqual(parser.parse_args([]).refresh_interval, 30)
        self.assertEqual(parser.parse_args(["--refresh-interval", "15"]).refresh_interval, 15)
        self.assertEqual(parser.parse_args(["--refresh-interval", "300"]).refresh_interval, 300)
        self.assertIn("12 seconds", parser.format_help())

    def test_rejects_values_outside_bounds(self) -> None:
        parser = clawbar_collect.build_parser()

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["--refresh-interval", "14"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["--refresh-interval", "301"])


if __name__ == "__main__":
    unittest.main()
