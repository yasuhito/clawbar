from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from scripts import clawbar_collect


class CollectorFixture:
    """Shared setup for collector tests.

    ``collect()`` runs one collection in-process through a Gateway Command Surface.
    ``run_external()`` starts the real collector script with a minimal fake ``openclaw``
    on PATH, for the few tests about the process itself (deadline, termination, entry
    points). Incident notifications always reach a fake ``notify-send`` on PATH.
    """

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.snapshot_path = self.root / "state" / "clawbar" / "snapshot.json"
        self.command_path = self.root / "openclaw"
        self.notification_path = self.root / "notify-send"
        self.notification_log_path = self.root / "notifications.jsonl"
        self.command_path.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import os
                import sys
                import time

                arguments = sys.argv[1:]
                scenario = os.environ.get("FAKE_SCENARIO", "local")

                pid_path = os.environ.get("FAKE_PID_PATH")
                if pid_path:
                    with open(pid_path, "w", encoding="utf-8") as pid_file:
                        pid_file.write(str(os.getpid()))

                if arguments[:3] == ["node", "status", "--json"]:
                    time.sleep(float(os.environ.get("FAKE_NODE_DELAY", "0")))
                    if scenario == "node_host":
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
                    oversize = os.environ.get("FAKE_GATEWAY_OUTPUT_BYTES")
                    if oversize is not None:
                        remaining = int(oversize)
                        while remaining:
                            written = min(65536, remaining)
                            os.write(sys.stdout.fileno(), b"x" * written)
                            remaining -= written
                        raise SystemExit(0)
                    if scenario == "node_host" and "--url" not in arguments:
                        sys.stdout.write("connection broken")
                        sys.stderr.write("invalid token")
                        raise SystemExit(9)
                    sys.stderr.write(os.environ.get("FAKE_STDERR", ""))
                    output = os.environ.get("FAKE_STDOUT")
                    if output is None:
                        if scenario == "node_host":
                            url = arguments[arguments.index("--url") + 1]
                        else:
                            url = "ws://127.0.0.1:18789"
                        output = json.dumps({"rpc": {"ok": True, "url": url}})
                    sys.stdout.write(output)
                    raise SystemExit(int(os.environ.get("FAKE_EXIT", "0")))

                if arguments[:3] == ["nodes", "status", "--json"]:
                    sys.stdout.write(json.dumps({"nodes": []}))
                    raise SystemExit(0)
                if arguments[:3] == ["gateway", "call", "agents.list"]:
                    sys.stdout.write(json.dumps({"agents": []}))
                    raise SystemExit(0)
                if arguments[:3] == ["gateway", "call", "tasks.list"]:
                    sys.stdout.write(json.dumps({"tasks": []}))
                    raise SystemExit(0)
                if arguments[:3] == ["gateway", "call", "cron.list"]:
                    sys.stdout.write(json.dumps({"jobs": []}))
                    raise SystemExit(0)

                raise SystemExit(64)
                """
            ),
            encoding="utf-8",
        )
        self.command_path.chmod(0o755)
        self.notification_path.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import os
                import sys

                with open(os.environ["FAKE_NOTIFICATION_LOG"], "a", encoding="utf-8") as log:
                    log.write(json.dumps(sys.argv[1:]) + "\\n")
                raise SystemExit(int(os.environ.get("FAKE_NOTIFICATION_EXIT", "0")))
                """
            ),
            encoding="utf-8",
        )
        self.notification_path.chmod(0o755)

    @contextlib.contextmanager
    def fake_environment(self, **values: str):
        updates = {
            "FAKE_SCENARIO": "local",
            "FAKE_NODE_DELAY": "0",
            "FAKE_GATEWAY_DELAY": "0",
            "FAKE_STDERR": "diagnostic output is ignored",
            "FAKE_NOTIFICATION_LOG": str(self.notification_log_path),
            "FAKE_NOTIFICATION_EXIT": "0",
            "PATH": f"{self.root}{os.pathsep}{os.environ['PATH']}",
            "XDG_RUNTIME_DIR": str(self.root / "runtime"),
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

    def collect(
        self,
        commands: object,
        *,
        snapshot_path: Path | None = None,
        candidate_key: str | None = None,
        deadline: float = 1,
        secret: bytes | None = b"clawbar-test-node-key-secret-32!",
        **environment: str,
    ) -> clawbar_collect.CollectionResult:
        """Run one collection in-process through the Gateway Command Surface ``commands``."""
        with self.fake_environment(**environment):
            return clawbar_collect.collect_gateway(
                snapshot_path or self.snapshot_path,
                refresh_interval=30,
                commands=commands,
                collection_deadline=deadline,
                local_key_secret=secret,
                candidate_key=candidate_key,
            )

    def run_external(
        self,
        scenario: str,
        *,
        timeout: float = 15,
        environment_overrides: dict[str, str] | None = None,
        collector_arguments: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.root}{os.pathsep}{environment['PATH']}",
                "XDG_STATE_HOME": str(self.root / "external-state"),
                "XDG_RUNTIME_DIR": str(self.root / "runtime"),
                "FAKE_SCENARIO": scenario,
                "FAKE_NOTIFICATION_LOG": str(self.notification_log_path),
                "FAKE_NOTIFICATION_EXIT": "0",
                **(environment_overrides or {}),
            }
        )
        return subprocess.run(
            [
                sys.executable,
                str(Path(clawbar_collect.__file__)),
                "--refresh-interval",
                "30",
                *(collector_arguments or []),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
            env=environment,
        )

    def read_snapshot(self) -> dict[str, object]:
        return json.loads(self.snapshot_path.read_text(encoding="utf-8"))

    def read_notifications(self) -> list[list[str]]:
        try:
            lines = self.notification_log_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        return [json.loads(line) for line in lines]
