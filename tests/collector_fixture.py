from __future__ import annotations

import contextlib
import json
import os
import tempfile
import textwrap
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
                node_key_secret=b"clawbar-test-node-key-secret-32!",
            )

    def read_snapshot(self) -> dict[str, object]:
        return json.loads(self.snapshot_path.read_text(encoding="utf-8"))

    def read_calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.call_log_path.read_text(encoding="utf-8").splitlines()]
