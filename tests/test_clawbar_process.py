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
    clawbar_cli,
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


class RefreshIntervalTests(unittest.TestCase):
    def test_collector_reexports_cli_main(self) -> None:
        self.assertIs(clawbar_collect.main, clawbar_cli.main)

    def test_accepts_bounds_and_default(self) -> None:
        parser = clawbar_cli.build_parser()

        self.assertEqual(parser.parse_args([]).refresh_interval, 30)
        self.assertEqual(parser.parse_args(["--refresh-interval", "15"]).refresh_interval, 15)
        self.assertEqual(parser.parse_args(["--refresh-interval", "300"]).refresh_interval, 300)
        self.assertIn("12 seconds", parser.format_help())

    def test_rejects_values_outside_bounds(self) -> None:
        parser = clawbar_cli.build_parser()

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["--refresh-interval", "14"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["--refresh-interval", "301"])


if __name__ == "__main__":
    unittest.main()
