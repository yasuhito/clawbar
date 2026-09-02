"""Gateway Command Surface: the port between the collector and the OpenClaw / Tailscale CLIs.

The collector asks seven named questions through this port and reads each answer as
(return code, stdout, stderr). Decoding stays on the collector side: a failed
``gateway status`` still carries structured JSON that ``automatic_resolution_missing``
must read. Notifications (``notify-send``) are not questions and stay outside the port.
Two adapters justify the seam: ``SubprocessCommandSurface`` in production and the
in-memory fake in ``tests/``.
"""

from __future__ import annotations

import ctypes
import json
import os
import selectors
import signal
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

if __package__:
    from .clawbar_bounds import MAX_COLLECTION_BYTES, MAX_METADATA_ITEMS
else:
    from clawbar_bounds import MAX_COLLECTION_BYTES, MAX_METADATA_ITEMS

OPENCLAW_COMMAND = ("openclaw",)
TAILSCALE_COMMAND = ("tailscale",)
OPENCLAW_TIMEOUT_MILLISECONDS = 10_000
MAX_COMMAND_STREAM_BYTES = MAX_COLLECTION_BYTES
COMMAND_READ_CHUNK_BYTES = 64 * 1024
PR_SET_PDEATHSIG = 1

CommandResult = subprocess.CompletedProcess[str]


class CollectionDeadlineExceeded(Exception):
    pass


class CommandOutputExceeded(OSError):
    pass


def seconds_until_deadline(deadline_at: float) -> float:
    seconds = deadline_at - time.monotonic()
    if seconds <= 0:
        raise CollectionDeadlineExceeded
    return seconds


class GatewayCommandSurface(Protocol):
    """The seven questions the collector may ask before ``deadline_at`` (monotonic seconds).

    Every method returns the raw answer. Adapters may raise CollectionDeadlineExceeded,
    CommandOutputExceeded, or OSError; the collector maps those to snapshot states.
    """

    def gateway_status(
        self, deadline_at: float, url: str | None = None
    ) -> CommandResult: ...

    def node_status(self, deadline_at: float) -> CommandResult: ...

    def nodes_status(self, deadline_at: float, url: str | None) -> CommandResult: ...

    def agents_list(self, deadline_at: float, url: str | None) -> CommandResult: ...

    def tasks_list(self, deadline_at: float, url: str | None) -> CommandResult: ...

    def cron_list(
        self, deadline_at: float, url: str | None, params: dict[str, object]
    ) -> CommandResult: ...

    def tailscale_status(self, deadline_at: float) -> CommandResult: ...


@dataclass(frozen=True)
class SubprocessCommandSurface:
    """Production adapter: runs the CLIs as bounded child processes."""

    openclaw: Sequence[str] = OPENCLAW_COMMAND
    tailscale: Sequence[str] = TAILSCALE_COMMAND

    def gateway_status(
        self, deadline_at: float, url: str | None = None
    ) -> CommandResult:
        return self._openclaw(
            deadline_at, ("gateway", "status", "--json", "--require-rpc"), url
        )

    def node_status(self, deadline_at: float) -> CommandResult:
        return run_command([*self.openclaw, "node", "status", "--json"], deadline_at)

    def nodes_status(self, deadline_at: float, url: str | None) -> CommandResult:
        return self._openclaw(deadline_at, ("nodes", "status", "--json"), url)

    def agents_list(self, deadline_at: float, url: str | None) -> CommandResult:
        return self._openclaw(
            deadline_at,
            ("gateway", "call", "agents.list", "--params", "{}", "--json"),
            url,
        )

    def tasks_list(self, deadline_at: float, url: str | None) -> CommandResult:
        params = json.dumps({"limit": MAX_METADATA_ITEMS}, separators=(",", ":"))
        return self._openclaw(
            deadline_at,
            ("gateway", "call", "tasks.list", "--params", params, "--json"),
            url,
        )

    def cron_list(
        self, deadline_at: float, url: str | None, params: dict[str, object]
    ) -> CommandResult:
        encoded = json.dumps(params, separators=(",", ":"), sort_keys=True)
        return self._openclaw(
            deadline_at,
            ("gateway", "call", "cron.list", "--params", encoded, "--json"),
            url,
        )

    def tailscale_status(self, deadline_at: float) -> CommandResult:
        return run_command([*self.tailscale, "status", "--json"], deadline_at)

    def _openclaw(
        self, deadline_at: float, arguments: Sequence[str], url: str | None
    ) -> CommandResult:
        timeout = max(
            1,
            min(
                OPENCLAW_TIMEOUT_MILLISECONDS,
                int(seconds_until_deadline(deadline_at) * 1000),
            ),
        )
        command = [*self.openclaw, *arguments, "--timeout", str(timeout)]
        if url is not None:
            command.extend(["--url", url])
        return run_command(command, deadline_at)


def run_command(command: Sequence[str], deadline_at: float) -> CommandResult:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        preexec_fn=terminate_with_parent,  # noqa: PLW1509 -- PDEATHSIG 用。スレッドからは呼ばない
    )
    stdout = bytearray()
    stderr = bytearray()
    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    assert process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, stdout)
    selector.register(process.stderr, selectors.EVENT_READ, stderr)
    try:
        while selector.get_map():
            events = selector.select(seconds_until_deadline(deadline_at))
            for key, _ in events:
                output = key.data
                chunk = os.read(
                    key.fd,
                    min(
                        COMMAND_READ_CHUNK_BYTES,
                        MAX_COMMAND_STREAM_BYTES + 1 - len(output),
                    ),
                )
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                output.extend(chunk)
                if len(output) > MAX_COMMAND_STREAM_BYTES:
                    raise CommandOutputExceeded(
                        f"Command output exceeds {MAX_COMMAND_STREAM_BYTES} bytes"
                    )
        return_code = process.wait(timeout=seconds_until_deadline(deadline_at))
    except (subprocess.TimeoutExpired, CollectionDeadlineExceeded) as error:
        stop_process_group(process)
        raise CollectionDeadlineExceeded from error
    except BaseException:
        stop_process_group(process)
        raise
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    return subprocess.CompletedProcess(
        command,
        return_code,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def terminate_with_parent() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))
    if os.getppid() == 1:
        os.kill(os.getpid(), signal.SIGTERM)


def stop_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        try:
            process.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        process.wait()
