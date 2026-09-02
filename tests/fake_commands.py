"""In-memory Gateway Command Surface for tests: an answer table instead of a fake executable.

Each of the seven questions maps to one answer or a list of answers consumed in order
(the last one repeats). An answer is a CompletedProcess, an exception instance to raise,
or a callable that receives the question's details (``url``, ``params``) and returns one
of those. Unscripted questions answer with exit code 64, like an unknown subcommand.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

from scripts.clawbar_commands import CommandResult

Answer = CommandResult | BaseException | Callable[..., "Answer"]

QUESTIONS = (
    "gateway_status",
    "node_status",
    "nodes_status",
    "agents_list",
    "tasks_list",
    "cron_list",
    "tailscale_status",
)
UNSCRIPTED_EXIT_CODE = 64
LOCAL_GATEWAY_URL = "ws://127.0.0.1:18789"


def ok(payload: object, stderr: str = "") -> CommandResult:
    """A successful answer whose stdout is ``payload`` as JSON."""
    return subprocess.CompletedProcess(("fake",), 0, json.dumps(payload), stderr)


def text(stdout: str, returncode: int = 0, stderr: str = "") -> CommandResult:
    """An answer with literal stdout, for malformed or misleading output."""
    return subprocess.CompletedProcess(("fake",), returncode, stdout, stderr)


def failed(returncode: int = 9, stdout: str = "", stderr: str = "") -> CommandResult:
    """A failed answer."""
    return subprocess.CompletedProcess(("fake",), returncode, stdout, stderr)


def gateway_ok(url: str = LOCAL_GATEWAY_URL) -> CommandResult:
    """The healthy ``gateway status`` answer for a Gateway reachable at ``url``."""
    return ok({"rpc": {"ok": True, "url": url}})


def node_not_hosting() -> CommandResult:
    """A ``node status`` answer for a device that hosts no Gateway."""
    return ok(
        {
            "service": {
                "loaded": False,
                "command": None,
                "runtime": {"status": "stopped", "state": "inactive"},
            }
        }
    )


def node_hosting(
    host: str = "node-gateway.example.test",
    port: int = 18789,
    tls: bool = True,
    context_path: str = "/openclaw-gw",
) -> CommandResult:
    """A ``node status`` answer for a device whose OpenClaw node run hosts a Gateway."""
    arguments = [
        "/usr/bin/node",
        "/opt/openclaw.mjs",
        "node",
        "run",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if tls:
        arguments.append("--tls")
    if context_path:
        arguments.extend(["--context-path", context_path])
    return ok(
        {
            "service": {
                "loaded": True,
                "command": {"programArguments": arguments},
                "runtime": {"status": "running", "state": "active"},
            }
        }
    )


def gateway_unresolved() -> CommandResult:
    """A failed local ``gateway status`` whose JSON shows no loaded service (automatic resolution missing)."""
    return failed(
        9,
        json.dumps(
            {
                "service": {"loaded": False, "runtime": {"status": "stopped"}},
                "rpc": {"ok": False, "url": LOCAL_GATEWAY_URL},
            }
        ),
        "invalid token",
    )


def echo_dialed_url(reported_url: str | None = None) -> Callable[..., CommandResult]:
    """A ``gateway status`` answer that reports the dialed ``--url`` (or ``reported_url``)."""

    def answer(url: str | None = None) -> CommandResult:
        return gateway_ok(reported_url or url or LOCAL_GATEWAY_URL)

    return answer


class FakeCommandSurface:
    """Answers the seven questions from a table and records every call in order."""

    def __init__(self, **answers: Answer | list[Answer]) -> None:
        unknown = set(answers) - set(QUESTIONS)
        if unknown:
            raise ValueError(f"Unknown questions: {sorted(unknown)}")
        self.answers: dict[str, list[Answer]] = {
            question: list(answer) if isinstance(answer, list) else [answer]
            for question, answer in answers.items()
        }
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.deadlines: list[float] = []

    @classmethod
    def healthy(
        cls, url: str = LOCAL_GATEWAY_URL, **answers: Answer | list[Answer]
    ) -> FakeCommandSurface:
        """A local healthy Gateway with empty metadata; ``answers`` override any question."""
        defaults: dict[str, Answer | list[Answer]] = {
            "gateway_status": gateway_ok(url),
            "nodes_status": ok({"nodes": []}),
            "agents_list": ok({"agents": []}),
            "tasks_list": ok({"tasks": []}),
            "cron_list": ok({"jobs": []}),
        }
        defaults.update(answers)
        return cls(**defaults)

    @classmethod
    def lost(
        cls,
        stdout: str = "connection broken",
        returncode: int = 9,
        **answers: Answer | list[Answer],
    ) -> FakeCommandSurface:
        """A Gateway that no longer answers and a device that hosts none; ``answers`` override any question."""
        defaults: dict[str, Answer | list[Answer]] = {
            "gateway_status": failed(returncode, stdout, "invalid token"),
            "node_status": node_not_hosting(),
        }
        defaults.update(answers)
        return cls(**defaults)

    def questions(self) -> list[str]:
        """Every question asked, in order."""
        return [name for name, _ in self.calls]

    def asked(self, question: str) -> list[dict[str, Any]]:
        """Details (``url``, ``params``) of every call to ``question``, in order."""
        return [details for name, details in self.calls if name == question]

    def _answer(
        self, question: str, deadline_at: float, **details: Any
    ) -> CommandResult:
        self.calls.append((question, details))
        self.deadlines.append(deadline_at)
        queue = self.answers.get(question)
        if not queue:
            return failed(UNSCRIPTED_EXIT_CODE)
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        while callable(answer):
            answer = answer(**details)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def gateway_status(
        self, deadline_at: float, url: str | None = None
    ) -> CommandResult:
        return self._answer("gateway_status", deadline_at, url=url)

    def node_status(self, deadline_at: float) -> CommandResult:
        return self._answer("node_status", deadline_at)

    def nodes_status(self, deadline_at: float, url: str | None) -> CommandResult:
        return self._answer("nodes_status", deadline_at, url=url)

    def agents_list(self, deadline_at: float, url: str | None) -> CommandResult:
        return self._answer("agents_list", deadline_at, url=url)

    def tasks_list(self, deadline_at: float, url: str | None) -> CommandResult:
        return self._answer("tasks_list", deadline_at, url=url)

    def cron_list(
        self, deadline_at: float, url: str | None, params: dict[str, object]
    ) -> CommandResult:
        return self._answer("cron_list", deadline_at, url=url, params=params)

    def tailscale_status(self, deadline_at: float) -> CommandResult:
        return self._answer("tailscale_status", deadline_at)
