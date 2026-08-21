from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import datetime
from pathlib import Path

from scripts import clawbar_collect


class CollectorFixture:
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.snapshot_path = self.root / "state" / "clawbar" / "snapshot.json"
        self.command_path = self.root / "openclaw"
        self.call_log_path = self.root / "calls.jsonl"
        self.command_path.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import os
                import sys
                import time

                arguments = sys.argv[1:]
                with open(os.environ["FAKE_CALL_LOG"], "a", encoding="utf-8") as log:
                    log.write(json.dumps(arguments) + "\\n")

                if arguments[:3] == ["node", "status", "--json"]:
                    time.sleep(float(os.environ.get("FAKE_NODE_DELAY", "0")))
                    if os.environ.get("FAKE_SCENARIO") == "node_host":
                        print(json.dumps({
                            "service": {
                                "loaded": True,
                                "command": {"programArguments": [
                                    "/usr/bin/node", "/opt/openclaw.mjs", "node", "run",
                                    "--host", "node-gateway.example.test", "--port", "18789",
                                    "--tls", "--context-path", "/openclaw-gw"
                                ]},
                                "runtime": {"status": "running", "state": "active"}
                            }
                        }))
                    else:
                        print(json.dumps({
                            "service": {
                                "loaded": False,
                                "command": None,
                                "runtime": {"status": "stopped", "state": "inactive"}
                            }
                        }))
                    raise SystemExit(0)

                if arguments[:3] == ["nodes", "status", "--json"]:
                    time.sleep(float(os.environ.get("FAKE_NODES_DELAY", "0")))
                    output = os.environ.get("FAKE_NODES")
                    if output is None:
                        output = json.dumps({"nodes": []})
                    sys.stdout.write(output)
                    raise SystemExit(int(os.environ.get("FAKE_NODES_EXIT", "0")))

                if arguments[:3] == ["gateway", "call", "agents.list"]:
                    output = os.environ.get("FAKE_AGENTS")
                    if output is None:
                        output = json.dumps({"agents": []})
                    sys.stdout.write(output)
                    raise SystemExit(int(os.environ.get("FAKE_AGENTS_EXIT", "0")))

                if arguments[:3] == ["gateway", "call", "tasks.list"]:
                    output = os.environ.get("FAKE_TASKS")
                    if output is None:
                        output = json.dumps({"tasks": []})
                    sys.stdout.write(output)
                    raise SystemExit(int(os.environ.get("FAKE_TASKS_EXIT", "0")))

                if arguments[:2] == ["gateway", "status"]:
                    time.sleep(float(os.environ.get("FAKE_GATEWAY_DELAY", "0")))
                    scenario = os.environ.get("FAKE_SCENARIO", "local")
                    if scenario == "node_host" and "--url" not in arguments:
                        sys.stdout.write("connection broken")
                        sys.stderr.write("invalid token")
                        raise SystemExit(9)
                    sys.stderr.write(os.environ.get("FAKE_STDERR", ""))
                    output = os.environ.get("FAKE_STDOUT")
                    if output is None:
                        if scenario == "node_host":
                            url = arguments[arguments.index("--url") + 1]
                        elif scenario == "configured_remote":
                            url = "wss://configured-gateway.example.test:18789"
                        else:
                            url = "ws://127.0.0.1:18789"
                        output = json.dumps({"rpc": {"ok": True, "url": url}})
                    sys.stdout.write(output)
                    raise SystemExit(int(os.environ.get("FAKE_EXIT", "0")))

                raise SystemExit(64)
                """
            ),
            encoding="utf-8",
        )
        self.command_path.chmod(0o755)

    @contextlib.contextmanager
    def fake_environment(self, **values: str):
        updates = {
            "FAKE_CALL_LOG": str(self.call_log_path),
            "FAKE_SCENARIO": "local",
            "FAKE_NODE_DELAY": "0",
            "FAKE_NODES_DELAY": "0",
            "FAKE_GATEWAY_DELAY": "0",
            "FAKE_STDERR": "diagnostic output is ignored",
            **values,
        }
        previous = {name: os.environ.get(name) for name in updates}
        os.environ.update(updates)
        try:
            yield
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def run_collector(
        self,
        *,
        stdout: str | None = None,
        stderr: str = "diagnostic output is ignored",
        exit_code: int = 0,
        node_delay: float = 0,
        nodes_delay: float = 0,
        gateway_delay: float = 0,
        deadline: float = 1,
        scenario: str = "local",
    ) -> clawbar_collect.CollectionResult:
        values = {
            "FAKE_EXIT": str(exit_code),
            "FAKE_NODE_DELAY": str(node_delay),
            "FAKE_NODES_DELAY": str(nodes_delay),
            "FAKE_GATEWAY_DELAY": str(gateway_delay),
            "FAKE_STDERR": stderr,
            "FAKE_SCENARIO": scenario,
        }
        if stdout is not None:
            values["FAKE_STDOUT"] = stdout
        with self.fake_environment(**values):
            return clawbar_collect.collect_gateway(
                self.snapshot_path,
                refresh_interval=30,
                openclaw_command=[str(self.command_path)],
                collection_deadline=deadline,
            )

    def read_snapshot(self) -> dict[str, object]:
        return json.loads(self.snapshot_path.read_text(encoding="utf-8"))

    def read_calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.call_log_path.read_text(encoding="utf-8").splitlines()]

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
        self.assertNotEqual(self.read_snapshot()["gateway"], {"state": "unstable"})

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
    def run_external(
        self,
        scenario: str,
        *,
        timeout: float = 15,
        environment_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.root}{os.pathsep}{environment['PATH']}",
                "XDG_STATE_HOME": str(self.root / "external-state"),
                "FAKE_CALL_LOG": str(self.call_log_path),
                "FAKE_SCENARIO": scenario,
                **(environment_overrides or {}),
            }
        )
        return subprocess.run(
            [sys.executable, str(Path(clawbar_collect.__file__)), "--refresh-interval", "30"],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
            env=environment,
        )

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
                self.assertEqual(len(calls), metadata_offset + 3)

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
                {"displayName": "studio-ops", "connected": True},
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
        self.assertEqual(json.loads(failed.stdout)["gateway"], {"state": "unknown"})
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
