#!/usr/bin/env python3
"""Collect one structured OpenClaw Gateway status into Clawbar's cache."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
DEFAULT_REFRESH_INTERVAL_SECONDS = 30
MIN_REFRESH_INTERVAL_SECONDS = 15
MAX_REFRESH_INTERVAL_SECONDS = 300
COLLECTION_DEADLINE_SECONDS = 12.0
SNAPSHOT_WRITE_RESERVE_SECONDS = 0.5
OPENCLAW_TIMEOUT_MILLISECONDS = 10_000


class ExitCode(IntEnum):
    OK = 0
    COMMAND_FAILED = 20
    COMMAND_TIMEOUT = 21
    MALFORMED_JSON = 22
    UNSUPPORTED_JSON = 23


@dataclass(frozen=True)
class CollectionResult:
    exit_code: ExitCode
    snapshot: dict[str, Any]


@dataclass(frozen=True)
class GatewayTarget:
    url: str
    source: str


class CollectionDeadlineExceeded(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_snapshot_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "clawbar" / "snapshot.json"


def parse_refresh_interval(value: str) -> int:
    try:
        interval = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("refresh interval must be an integer") from error
    if not MIN_REFRESH_INTERVAL_SECONDS <= interval <= MAX_REFRESH_INTERVAL_SECONDS:
        raise argparse.ArgumentTypeError("refresh interval must be between 15 and 300 seconds")
    return interval


def load_previous_snapshot(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("schemaVersion") != SCHEMA_VERSION:
        return None
    return value


def remaining_budget(deadline_at: float) -> float:
    remaining = deadline_at - time.monotonic()
    if remaining <= 0:
        raise CollectionDeadlineExceeded
    return remaining


def run_command(command: Sequence[str], deadline_at: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=remaining_budget(deadline_at),
        )
    except subprocess.TimeoutExpired as error:
        raise CollectionDeadlineExceeded from error


def command_option(arguments: Sequence[str], option: str) -> str | None:
    try:
        index = arguments.index(option)
    except ValueError:
        return None
    if index + 1 >= len(arguments):
        return None
    value = arguments[index + 1]
    return value if value and not value.startswith("--") else None


def node_host_target(status: object) -> GatewayTarget | None:
    if not isinstance(status, dict):
        return None
    service = status.get("service")
    if not isinstance(service, dict) or service.get("loaded") is not True:
        return None
    runtime = service.get("runtime")
    if not isinstance(runtime, dict):
        return None
    if runtime.get("status") != "running" and runtime.get("state") != "active":
        return None
    command = service.get("command")
    if not isinstance(command, dict):
        return None
    arguments = command.get("programArguments")
    if not isinstance(arguments, list) or not all(isinstance(value, str) for value in arguments):
        return None
    if not any(arguments[index : index + 2] == ["node", "run"] for index in range(len(arguments) - 1)):
        return None

    host = command_option(arguments, "--host")
    port_text = command_option(arguments, "--port")
    if host is None or port_text is None or any(character in host for character in "/@?#"):
        return None
    try:
        port = int(port_text)
    except ValueError:
        return None
    if not 1 <= port <= 65535:
        return None

    context_path = command_option(arguments, "--context-path") or ""
    if context_path and (not context_path.startswith("/") or "?" in context_path or "#" in context_path):
        return None
    try:
        parsed_ip = ipaddress.ip_address(host)
        url_host = f"[{host}]" if parsed_ip.version == 6 else host
    except ValueError:
        if not host.strip() or any(character.isspace() for character in host):
            return None
        url_host = host
    scheme = "wss" if "--tls" in arguments else "ws"
    return GatewayTarget(f"{scheme}://{url_host}:{port}{context_path}", "node_host")


def resolution_source(status: dict[str, Any], source_hint: str | None = None) -> str | None:
    rpc = status.get("rpc")
    if not isinstance(rpc, dict) or rpc.get("ok") is not True:
        return None
    url = rpc.get("url")
    if not isinstance(url, str):
        return None
    hostname = urlsplit(url).hostname
    if hostname is None:
        return None
    if source_hint == "node_host":
        return source_hint
    if hostname.lower() == "localhost":
        return "local"
    try:
        return "local" if ipaddress.ip_address(hostname).is_loopback else "configured_remote"
    except ValueError:
        return "configured_remote"


def healthy_snapshot(
    status: dict[str, Any],
    refresh_interval: int,
    generated_at: str,
    source_hint: str | None = None,
) -> dict[str, Any] | None:
    source = resolution_source(status, source_hint)
    if source is None:
        return None
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "refreshIntervalSeconds": refresh_interval,
        "resolutionSource": source,
        "gateway": {"state": "healthy"},
        "lastSuccessAt": generated_at,
        "consecutiveFailures": 0,
    }


def failure_snapshot(
    previous: dict[str, Any] | None,
    refresh_interval: int,
    generated_at: str,
    failure_kind: str,
) -> dict[str, Any]:
    previous_failures = previous.get("consecutiveFailures", 0) if previous else 0
    failures = previous_failures + 1 if isinstance(previous_failures, int) else 1
    last_success = previous.get("lastSuccessAt") if previous else None
    source = previous.get("resolutionSource") if previous else None
    allowed_sources = {"local", "configured_remote", "node_host"}
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "refreshIntervalSeconds": refresh_interval,
        "resolutionSource": source if source in allowed_sources else "unresolved",
        "gateway": {"state": "unstable" if failures == 1 else "offline"},
        "lastSuccessAt": last_success if isinstance(last_success, str) else None,
        "consecutiveFailures": failures,
        "failureKind": failure_kind,
    }


def atomic_write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(snapshot, output, separators=(",", ":"), sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def publish_failure(
    snapshot_path: Path,
    previous: dict[str, Any] | None,
    refresh_interval: int,
    generated_at: str,
    exit_code: ExitCode,
    failure_kind: str,
) -> CollectionResult:
    snapshot = failure_snapshot(previous, refresh_interval, generated_at, failure_kind)
    atomic_write_snapshot(snapshot_path, snapshot)
    return CollectionResult(exit_code, snapshot)


def discover_node_host(openclaw_command: Sequence[str], deadline_at: float) -> GatewayTarget | None:
    completed = run_command([*openclaw_command, "node", "status", "--json"], deadline_at)
    if completed.returncode != 0:
        return None
    try:
        status = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return node_host_target(status)


def collect_gateway(
    snapshot_path: Path,
    refresh_interval: int,
    openclaw_command: Sequence[str] = ("openclaw",),
    collection_deadline: float = COLLECTION_DEADLINE_SECONDS,
) -> CollectionResult:
    deadline_at = time.monotonic() + collection_deadline
    command_deadline_at = deadline_at - min(SNAPSHOT_WRITE_RESERVE_SECONDS, collection_deadline / 10)
    generated_at = utc_now()
    previous = load_previous_snapshot(snapshot_path)

    try:
        target = discover_node_host(openclaw_command, command_deadline_at)
        remaining_milliseconds = max(
            1,
            min(OPENCLAW_TIMEOUT_MILLISECONDS, int(remaining_budget(command_deadline_at) * 1000)),
        )
        gateway_command = [
            *openclaw_command,
            "gateway",
            "status",
            "--json",
            "--require-rpc",
            "--timeout",
            str(remaining_milliseconds),
        ]
        if target is not None:
            gateway_command.extend(["--url", target.url])
        completed = run_command(gateway_command, command_deadline_at)
    except CollectionDeadlineExceeded:
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
            generated_at,
            ExitCode.COMMAND_TIMEOUT,
            "timeout",
        )
    except OSError:
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
            generated_at,
            ExitCode.COMMAND_FAILED,
            "command_failed",
        )

    if completed.returncode != 0:
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
            generated_at,
            ExitCode.COMMAND_FAILED,
            "command_failed",
        )

    try:
        status = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
            generated_at,
            ExitCode.MALFORMED_JSON,
            "malformed_json",
        )

    if not isinstance(status, dict):
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
            generated_at,
            ExitCode.UNSUPPORTED_JSON,
            "unsupported_json",
        )

    snapshot = healthy_snapshot(status, refresh_interval, generated_at, target.source if target else None)
    if snapshot is None:
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
            generated_at,
            ExitCode.UNSUPPORTED_JSON,
            "unsupported_json",
        )

    try:
        remaining_budget(deadline_at)
    except CollectionDeadlineExceeded:
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
            generated_at,
            ExitCode.COMMAND_TIMEOUT,
            "timeout",
        )
    atomic_write_snapshot(snapshot_path, snapshot)
    return CollectionResult(ExitCode.OK, snapshot)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"{__doc__} The whole collection exits within {int(COLLECTION_DEADLINE_SECONDS)} seconds."
    )
    parser.add_argument(
        "--refresh-interval",
        default=DEFAULT_REFRESH_INTERVAL_SECONDS,
        type=parse_refresh_interval,
        metavar="SECONDS",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    result = collect_gateway(default_snapshot_path(), arguments.refresh_interval)
    json.dump(result.snapshot, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
