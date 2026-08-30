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


class MetadataTests(unittest.TestCase):
    def test_secret_created_by_another_collector_is_validated(self) -> None:
        with (
            mock.patch.object(
                clawbar_metadata,
                "read_bounded_regular_file",
                side_effect=[FileNotFoundError, b""],
            ),
            mock.patch.object(os, "open", side_effect=FileExistsError),
        ):
            with self.assertRaisesRegex(OSError, "Invalid Clawbar local key secret"):
                clawbar_metadata.load_local_key_secret()

    def test_secret_reader_rejects_symbolic_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            secret_directory = root / "clawbar"
            secret_directory.mkdir()
            target = root / "outside-secret"
            target.write_bytes(b"x" * 32)
            (secret_directory / "node-key-secret").symlink_to(target)

            with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(root)}):
                with self.assertRaises(OSError):
                    clawbar_metadata.load_local_key_secret()


class BoundedInputTests(unittest.TestCase):
    def test_gateway_command_rejects_output_over_the_limit(self) -> None:
        for descriptor in (1, 2):
            with self.subTest(descriptor=descriptor), self.assertRaises(OSError):
                clawbar_commands.run_command(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import os; os.write("
                            f"{descriptor}, b'x' * ({clawbar_commands.MAX_COMMAND_STREAM_BYTES} + 1))"
                        ),
                    ],
                    time.monotonic() + 2,
                )

    def test_snapshot_reader_rejects_symbolic_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            target = root / "outside.json"
            target.write_text('{"schemaVersion":1}', encoding="utf-8")
            link = root / "snapshot.json"
            link.symlink_to(target)

            self.assertIsNone(clawbar_snapshot.read_json_document(link))

    def test_snapshot_reader_rejects_files_over_the_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot = Path(temporary_directory) / "snapshot.json"
            with snapshot.open("wb") as output:
                output.truncate(clawbar_snapshot.MAX_STATE_FILE_BYTES + 1)

            self.assertIsNone(clawbar_snapshot.read_json_document(snapshot))

    def test_snapshot_reader_rejects_fifo_without_waiting_for_a_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fifo = Path(temporary_directory) / "snapshot.json"
            os.mkfifo(fifo)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        "from scripts.clawbar_snapshot import read_json_document; "
                        "print(read_json_document(Path(r'" + str(fifo) + "')))"
                    ),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=0.5,
                check=True,
            )
            self.assertEqual(completed.stdout, "None\n")


class SubprocessCommandSurfaceTests(unittest.TestCase):
    """The production adapter builds each CLI command line; the collector never sees argv."""

    echo = (sys.executable, "-c", "import sys; print(' '.join(sys.argv[1:]))")

    def test_openclaw_questions_carry_a_bounded_timeout_and_the_target_url(self) -> None:
        surface = SubprocessCommandSurface(openclaw=self.echo)
        deadline_at = time.monotonic() + 2

        status = surface.gateway_status(deadline_at, "wss://example.test").stdout.split()
        nodes = surface.nodes_status(deadline_at, None).stdout.split()
        node = surface.node_status(deadline_at).stdout.split()

        self.assertEqual(status[:4], ["gateway", "status", "--json", "--require-rpc"])
        self.assertEqual(status[-2:], ["--url", "wss://example.test"])
        self.assertEqual(status[4], "--timeout")
        self.assertTrue(1 <= int(status[5]) <= 2000)
        self.assertEqual(nodes[:3], ["nodes", "status", "--json"])
        self.assertNotIn("--url", nodes)
        self.assertEqual(node, ["node", "status", "--json"])

    def test_gateway_calls_encode_their_params_compactly(self) -> None:
        surface = SubprocessCommandSurface(openclaw=self.echo)
        deadline_at = time.monotonic() + 2

        tasks = surface.tasks_list(deadline_at, None).stdout
        cron = surface.cron_list(deadline_at, None, {"offset": 0, "limit": 200, "includeDisabled": True}).stdout
        agents = surface.agents_list(deadline_at, None).stdout

        self.assertIn('gateway call tasks.list --params {"limit":500} --json', tasks)
        self.assertIn('gateway call cron.list --params {"includeDisabled":true,"limit":200,"offset":0} --json', cron)
        self.assertIn("gateway call agents.list --params {} --json", agents)

    def test_tailscale_status_uses_its_own_executable(self) -> None:
        surface = SubprocessCommandSurface(openclaw=("false",), tailscale=self.echo)

        completed = surface.tailscale_status(time.monotonic() + 2)

        self.assertEqual(completed.stdout.split(), ["status", "--json"])


class CollectorProcessTests(CollectorFixture, unittest.TestCase):
    """Behaviour that only the real collector process shows: deadlines, termination, bounds."""

    def test_executable_termination_stops_running_gateway_command(self) -> None:
        self._assert_executable_termination_stops_running_gateway_command("terminate")

    def test_executable_forced_termination_stops_running_gateway_command(self) -> None:
        self._assert_executable_termination_stops_running_gateway_command("kill")

    def _assert_executable_termination_stops_running_gateway_command(self, method: str) -> None:
        pid_path = self.root / "gateway-command.pid"
        child_pid: int | None = None
        collector: subprocess.Popen[str] | None = None
        with self.fake_environment(
            FAKE_GATEWAY_DELAY="30",
            FAKE_PID_PATH=str(pid_path),
            XDG_STATE_HOME=str(self.root / "termination-state"),
        ):
            collector = subprocess.Popen(
                [sys.executable, str(Path(clawbar_collect.__file__))],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=os.environ.copy(),
            )
            try:
                started_deadline = time.monotonic() + 2
                while not pid_path.exists() and time.monotonic() < started_deadline:
                    self.assertIsNone(collector.poll())
                    time.sleep(0.01)
                self.assertTrue(pid_path.exists(), "Gateway command did not start")
                child_pid = int(pid_path.read_text(encoding="utf-8"))

                getattr(collector, method)()
                collector.wait(timeout=2)

                stopped_deadline = time.monotonic() + 1
                while self._process_exists(child_pid) and time.monotonic() < stopped_deadline:
                    time.sleep(0.01)
                self.assertFalse(
                    self._process_exists(child_pid),
                    "Gateway command survived collector termination: "
                    + self._process_state(child_pid),
                )
            finally:
                if collector.poll() is None:
                    collector.kill()
                    collector.wait(timeout=2)
                if child_pid is not None and self._process_exists(child_pid):
                    os.kill(child_pid, signal.SIGKILL)

    @staticmethod
    def _process_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    @staticmethod
    def _process_state(pid: int) -> str:
        try:
            status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
        except FileNotFoundError:
            return "gone"
        return next((line for line in status.splitlines() if line.startswith("State:")), "unknown")

    def test_executable_bounds_gateway_command_output(self) -> None:
        started_at = time.monotonic()
        result = self.run_external(
            "local",
            timeout=2,
            environment_overrides={
                "FAKE_GATEWAY_OUTPUT_BYTES": str(clawbar_commands.MAX_COMMAND_STREAM_BYTES + 1),
            },
        )

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(json.loads(result.stdout)["failureKind"], "command_failed")
        self.assertLess(time.monotonic() - started_at, 2)

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


class CollectorEntryPointTests(CollectorFixture, unittest.TestCase):
    def test_read_theme_colors_prints_a_valid_regular_file(self) -> None:
        colors_path = self.root / "colors.toml"
        colors = 'green = "#123456"\nyellow = "#abcdef"\n'
        colors_path.write_text(colors, encoding="utf-8")

        result = self.run_external(
            "local",
            timeout=1,
            collector_arguments=["--read-theme-colors", str(colors_path)],
        )

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.stdout, colors)

    def test_read_theme_colors_rejects_unsafe_files_without_blocking(self) -> None:
        colors_path = self.root / "colors.toml"
        os.mkfifo(colors_path)

        fifo_result = self.run_external(
            "local",
            timeout=1,
            collector_arguments=["--read-theme-colors", str(colors_path)],
        )

        self.assertEqual(fifo_result.returncode, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(fifo_result.stdout, "")

        colors_path.unlink()
        outside = self.root / "outside-colors.toml"
        outside.write_text('green = "#123456"\n', encoding="utf-8")
        colors_path.symlink_to(outside)

        link_result = self.run_external(
            "local",
            timeout=1,
            collector_arguments=["--read-theme-colors", str(colors_path)],
        )

        self.assertEqual(link_result.returncode, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(link_result.stdout, "")

        colors_path.unlink()
        with colors_path.open("wb") as output:
            output.truncate(clawbar_snapshot.MAX_STATE_FILE_BYTES + 1)

        oversized_result = self.run_external(
            "local",
            timeout=1,
            collector_arguments=["--read-theme-colors", str(colors_path)],
        )

        self.assertEqual(oversized_result.returncode, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(oversized_result.stdout, "")

    def test_read_cache_prints_a_valid_regular_snapshot(self) -> None:
        state_directory = self.root / "external-state" / "clawbar"
        state_directory.mkdir(parents=True)
        snapshot = {"schemaVersion": 1, "gateway": {"state": "healthy"}}
        (state_directory / "snapshot.json").write_text(
            json.dumps(snapshot),
            encoding="utf-8",
        )

        result = self.run_external(
            "local",
            timeout=1,
            collector_arguments=["--read-cache"],
        )

        self.assertEqual(result.returncode, clawbar_collect.ExitCode.OK)
        self.assertEqual(json.loads(result.stdout), snapshot)

    def test_read_cache_rejects_fifo_and_symbolic_link_state(self) -> None:
        state_directory = self.root / "external-state" / "clawbar"
        state_directory.mkdir(parents=True)
        snapshot_path = state_directory / "snapshot.json"
        os.mkfifo(snapshot_path)

        fifo_result = self.run_external(
            "local",
            timeout=1,
            collector_arguments=["--read-cache"],
        )

        self.assertEqual(fifo_result.returncode, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(fifo_result.stdout, "")

        snapshot_path.unlink()
        outside = self.root / "outside.json"
        outside.write_text('{"schemaVersion":1,"private":"sentinel"}', encoding="utf-8")
        snapshot_path.symlink_to(outside)

        link_result = self.run_external(
            "local",
            timeout=1,
            collector_arguments=["--read-cache"],
        )

        self.assertEqual(link_result.returncode, clawbar_collect.ExitCode.COMMAND_FAILED)
        self.assertEqual(link_result.stdout, "")
        self.assertIn("sentinel", outside.read_text(encoding="utf-8"))


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

    # ---- Gateway Target resolution ----

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

    # ---- Fleet, Agents, and Task Results ----

    def test_distinguishes_empty_fleet_from_missing_gateway(self) -> None:
        result = self.collect(FakeCommandSurface.healthy())

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "healthy"})
        self.assertEqual(result.snapshot["fleet"], {"available": True, "nodes": []})
        self.assertEqual(result.snapshot["agents"], {"available": True, "items": []})

    def test_sanitizes_registered_agents_and_task_results(self) -> None:
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

        result = self.collect(
            FakeCommandSurface.healthy(nodes_status=ok(nodes), agents_list=ok(agents), tasks_list=ok(tasks))
        )

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        snapshot = result.snapshot
        self.assertEqual([node["name"] for node in snapshot["fleet"]["nodes"]], ["Local", "studio-ops"])
        node_keys = [node["key"] for node in snapshot["fleet"]["nodes"]]
        self.assertEqual(len(set(node_keys)), 2)
        self.assertTrue(all(key.startswith("node:") for key in node_keys))
        by_name = {agent["name"]: agent for agent in snapshot["agents"]["items"]}
        self.assertNotIn("activity", by_name["planner"])
        self.assertEqual(by_name["planner"]["taskResult"]["state"], "failed")
        self.assertNotIn("activity", by_name["builder"])
        self.assertEqual(by_name["builder"]["taskResult"], {"state": "none"})
        self.assertNotIn("activity", by_name["observer"])
        self.assertEqual(by_name["observer"]["taskResult"]["state"], "succeeded")
        self.assertNotIn("activity", by_name["indexer"])
        self.assertEqual(by_name["indexer"]["taskResult"], {"state": "none"})
        self.assertEqual(snapshot["gateway"], {"state": "healthy"})
        serialized = json.dumps(snapshot)
        for sentinel in private_sentinels:
            self.assertNotIn(sentinel, serialized)

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

        first = self.collect(FakeCommandSurface.healthy(nodes_status=ok(first_nodes)))
        second = self.collect(FakeCommandSurface.healthy(nodes_status=ok(second_nodes)))
        replacement = self.collect(FakeCommandSurface.healthy(nodes_status=ok(replacement_nodes)))
        first_fleet = first.snapshot["fleet"]["nodes"]
        second_fleet = second.snapshot["fleet"]["nodes"]
        replacement_fleet = replacement.snapshot["fleet"]["nodes"]

        for result in (first, second, replacement):
            self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
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
        serialized = json.dumps([first.snapshot, second.snapshot, replacement.snapshot])
        self.assertNotIn("PRIVATE-NODE", serialized)
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

        result = self.collect(FakeCommandSurface.healthy(nodes_status=ok({"nodes": nodes})))
        fleet = result.snapshot["fleet"]["nodes"]

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(len(fleet), 1)
        self.assertEqual(fleet[0]["state"], "healthy")
        self.assertEqual(fleet[0]["version"], "current")

    def test_node_keys_stay_stable_without_runtime_directory(self) -> None:
        nodes = {"nodes": [{"nodeId": "PRIVATE-NODE", "displayName": "Local", "connected": True}]}
        environment = {"XDG_RUNTIME_DIR": "", "XDG_STATE_HOME": str(self.root / "state")}

        first = self.collect(FakeCommandSurface.healthy(nodes_status=ok(nodes)), secret=None, **environment)
        second = self.collect(FakeCommandSurface.healthy(nodes_status=ok(nodes)), secret=None, **environment)

        first_node = first.snapshot["fleet"]["nodes"][0]
        second_node = second.snapshot["fleet"]["nodes"][0]
        self.assertEqual(first.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(second.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(first_node["key"], second_node["key"])
        self.assertTrue(first_node["key"].startswith("node:"))
        self.assertNotIn("PRIVATE-NODE", json.dumps([first.snapshot, second.snapshot]))

    def test_invalid_node_key_secret_makes_fleet_unavailable(self) -> None:
        secret_path = self.root / "runtime" / "clawbar" / "node-key-secret"
        secret_path.parent.mkdir(parents=True)
        secret_path.write_bytes(b"invalid")
        nodes = {"nodes": [{"nodeId": "PRIVATE-NODE", "displayName": "Local", "connected": True}]}

        result = self.collect(FakeCommandSurface.healthy(nodes_status=ok(nodes)), secret=None)

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(result.snapshot["fleet"], {"available": False, "nodes": []})
        self.assertNotIn("PRIVATE-NODE", json.dumps(result.snapshot))

    def test_node_without_private_identity_makes_fleet_unavailable(self) -> None:
        nodes = {"nodes": [{"displayName": "Local", "connected": True}]}

        result = self.collect(FakeCommandSurface.healthy(nodes_status=ok(nodes)))

        self.assertEqual(result.exit_code, clawbar_collect.ExitCode.OK)
        self.assertEqual(result.snapshot["gateway"], {"state": "degraded"})
        self.assertEqual(result.snapshot["fleet"], {"available": False, "nodes": []})


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
