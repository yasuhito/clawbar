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

                if arguments[:2] == ["gateway", "status"]:
                    time.sleep(float(os.environ.get("FAKE_GATEWAY_DELAY", "0")))
                    sys.stderr.write(os.environ.get("FAKE_STDERR", ""))
                    output = os.environ.get("FAKE_STDOUT")
                    if output is None:
                        scenario = os.environ.get("FAKE_SCENARIO", "local")
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
        exit_code: int = 0,
        node_delay: float = 0,
        gateway_delay: float = 0,
        deadline: float = 1,
    ) -> clawbar_collect.CollectionResult:
        values = {
            "FAKE_EXIT": str(exit_code),
            "FAKE_NODE_DELAY": str(node_delay),
            "FAKE_GATEWAY_DELAY": str(gateway_delay),
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

    def test_nonzero_command_does_not_parse_misleading_stdout(self) -> None:
        status = {"rpc": {"ok": True, "url": "ws://127.0.0.1:18789"}}

        result = self.run_collector(stdout=json.dumps(status), exit_code=9)

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(self.read_snapshot()["gateway"], {"state": "unstable"})

    def test_deadline_is_shared_across_node_resolution_and_gateway_probe(self) -> None:
        started_at = time.monotonic()

        result = self.run_collector(node_delay=0.07, gateway_delay=0.07, deadline=0.11)

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.COMMAND_TIMEOUT)
        self.assertLess(time.monotonic() - started_at, 0.25)
        self.assertEqual(self.read_snapshot()["failureKind"], "timeout")

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
    def run_external(self, scenario: str, *, timeout: float = 15) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.root}{os.pathsep}{environment['PATH']}",
                "XDG_STATE_HOME": str(self.root / "external-state"),
                "FAKE_CALL_LOG": str(self.call_log_path),
                "FAKE_SCENARIO": scenario,
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
                self.assertEqual(calls[0], ["node", "status", "--json"])
                self.assertEqual(calls[1][:2], ["gateway", "status"])
                if scenario == "node_host":
                    url_index = calls[1].index("--url") + 1
                    self.assertEqual(
                        calls[1][url_index],
                        "wss://node-gateway.example.test:18789/openclaw-gw",
                    )
                    self.assertNotIn("node-gateway.example.test", result.stdout)
                else:
                    self.assertNotIn("--url", calls[1])

    def test_executable_enforces_default_twelve_second_whole_collection_deadline(self) -> None:
        started_at = time.monotonic()
        with self.fake_environment(FAKE_NODE_DELAY="30"):
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
