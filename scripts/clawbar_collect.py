#!/usr/bin/env python3
"""Collect one structured OpenClaw Gateway status into Clawbar's cache."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit

if __package__:
    from .clawbar_automation import (
        collect_automation_surface,
        collected_target_url,
        open_automation_history,
        target_state_path,
    )
    from .clawbar_incidents import process_incident_transitions
    from .clawbar_metadata import build_current_snapshot, load_node_key_secret, sanitize_metadata
    from .clawbar_snapshot import (
        atomic_write_snapshot,
        build_failure_snapshot,
        last_known_metadata,
        load_snapshot,
        utc_now,
    )
else:
    from clawbar_automation import (
        collect_automation_surface,
        collected_target_url,
        open_automation_history,
        target_state_path,
    )
    from clawbar_incidents import process_incident_transitions
    from clawbar_metadata import build_current_snapshot, load_node_key_secret, sanitize_metadata
    from clawbar_snapshot import (
        atomic_write_snapshot,
        build_failure_snapshot,
        last_known_metadata,
        load_snapshot,
        utc_now,
    )

SCHEMA_VERSION = 1
DEFAULT_REFRESH_INTERVAL_SECONDS = 30
MIN_REFRESH_INTERVAL_SECONDS = 15
MAX_REFRESH_INTERVAL_SECONDS = 300
COLLECTION_DEADLINE_SECONDS = 12.0
SNAPSHOT_WRITE_RESERVE_SECONDS = 0.5
OPENCLAW_TIMEOUT_MILLISECONDS = 10_000
RESOLUTION_SOURCES = frozenset({"local", "configured_remote", "node_host"})


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




def default_snapshot_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "clawbar" / "snapshot.json"





def validate_refresh_interval(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError
    try:
        interval = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError from error
    if isinstance(value, float) and not value.is_integer():
        raise ValueError
    if isinstance(value, str) and value.strip() != str(interval):
        raise ValueError
    if not MIN_REFRESH_INTERVAL_SECONDS <= interval <= MAX_REFRESH_INTERVAL_SECONDS:
        raise ValueError
    return interval


def parse_refresh_interval(value: str) -> int:
    try:
        return validate_refresh_interval(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("refresh interval must be an integer from 15 through 300 seconds") from error


def load_previous_snapshot(path: Path) -> dict[str, Any] | None:
    return load_snapshot(path, SCHEMA_VERSION)


def seconds_until_deadline(deadline_at: float) -> float:
    seconds = deadline_at - time.monotonic()
    if seconds <= 0:
        raise CollectionDeadlineExceeded
    return seconds


def run_command(command: Sequence[str], deadline_at: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=seconds_until_deadline(deadline_at),
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






def configuration_error_snapshot(
    previous: dict[str, Any] | None,
    refresh_interval: int,
    status: dict[str, Any],
    source_hint: str | None,
) -> dict[str, Any]:
    last_success = previous.get("lastSuccessAt") if previous else None
    source = resolution_source(status, source_hint)
    if source is None and previous:
        previous_source = previous.get("resolutionSource")
        source = previous_source if previous_source in RESOLUTION_SOURCES else None
    snapshot = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "refreshIntervalSeconds": refresh_interval,
        "resolutionSource": source or "unresolved",
        "gateway": {"state": "configuration_error"},
        "lastSuccessAt": last_success if isinstance(last_success, str) else None,
        "consecutiveFailures": 0,
        "failureKind": "unsupported_json",
    }
    retained = last_known_metadata(previous)
    if retained is not None:
        snapshot["lastKnown"] = retained
    return snapshot






def publish(snapshot_path: Path, exit_code: ExitCode, snapshot: dict[str, Any]) -> CollectionResult:
    atomic_write_snapshot(snapshot_path, snapshot)
    process_incident_transitions(snapshot)
    return CollectionResult(exit_code, snapshot)


def publish_failure(
    snapshot_path: Path,
    previous: dict[str, Any] | None,
    refresh_interval: int,
    exit_code: ExitCode,
    failure_kind: str,
) -> CollectionResult:
    return publish(
        snapshot_path,
        exit_code,
        build_failure_snapshot(
            previous,
            refresh_interval,
            failure_kind,
            SCHEMA_VERSION,
            RESOLUTION_SOURCES,
        ),
    )


def discover_node_host(openclaw_command: Sequence[str], deadline_at: float) -> GatewayTarget | None:
    completed = run_command([*openclaw_command, "node", "status", "--json"], deadline_at)
    if completed.returncode != 0:
        return None
    try:
        status = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return node_host_target(status)


def gateway_status_command(
    openclaw_command: Sequence[str],
    deadline_at: float,
    target: GatewayTarget | None = None,
) -> subprocess.CompletedProcess[str]:
    timeout_milliseconds = max(
        1,
        min(OPENCLAW_TIMEOUT_MILLISECONDS, int(seconds_until_deadline(deadline_at) * 1000)),
    )
    command = [
        *openclaw_command,
        "gateway",
        "status",
        "--json",
        "--require-rpc",
        "--timeout",
        str(timeout_milliseconds),
    ]
    if target is not None:
        command.extend(["--url", target.url])
    return run_command(command, deadline_at)

def metadata_command(
    openclaw_command: Sequence[str],
    arguments: Sequence[str],
    deadline_at: float,
    target: GatewayTarget | None,
) -> subprocess.CompletedProcess[str]:
    timeout_milliseconds = max(
        1,
        min(OPENCLAW_TIMEOUT_MILLISECONDS, int(seconds_until_deadline(deadline_at) * 1000)),
    )
    command = [*openclaw_command, *arguments, "--timeout", str(timeout_milliseconds)]
    if target is not None:
        command.extend(["--url", target.url])
    return run_command(command, deadline_at)


def decode_json(completed: subprocess.CompletedProcess[str]) -> object | None:
    if completed.returncode != 0:
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None

METADATA_SURFACES = (
    ("nodes", "status", "--json"),
    ("gateway", "call", "agents.list", "--params", "{}", "--json"),
    ("gateway", "call", "tasks.list", "--params", '{"limit":500}', "--json"),
)


def read_metadata_surface(
    openclaw_command: Sequence[str],
    arguments: Sequence[str],
    deadline_at: float,
    target: GatewayTarget | None,
) -> object | None:
    try:
        return decode_json(metadata_command(openclaw_command, arguments, deadline_at, target))
    except (CollectionDeadlineExceeded, OSError):
        return None




def collect_metadata(
    openclaw_command: Sequence[str],
    deadline_at: float,
    target: GatewayTarget | None,
) -> tuple[object | None, object | None, object | None, object | None]:
    core = tuple(
        read_metadata_surface(openclaw_command, arguments, deadline_at, target)
        for arguments in METADATA_SURFACES
    )
    def read_automation(arguments: Sequence[str]) -> object | None:
        return read_metadata_surface(openclaw_command, arguments, deadline_at, target)
    return (*core, collect_automation_surface(read_automation))



def publish_current(
    snapshot_path: Path,
    snapshot: dict[str, Any],
    target_url: str | None,
) -> CollectionResult:
    if target_url is None:
        return publish(snapshot_path, ExitCode.OK, snapshot)
    atomic_write_snapshot(
        target_state_path(snapshot_path),
        {
            "schemaVersion": SCHEMA_VERSION,
            "snapshotGeneratedAt": snapshot["generatedAt"],
            "url": target_url,
        },
    )
    return publish(snapshot_path, ExitCode.OK, snapshot)






def collect_gateway(
    snapshot_path: Path,
    refresh_interval: int,
    openclaw_command: Sequence[str] = ("openclaw",),
    collection_deadline: float = COLLECTION_DEADLINE_SECONDS,
    node_key_secret: bytes | None = None,
) -> CollectionResult:
    refresh_interval = validate_refresh_interval(refresh_interval)
    deadline_at = time.monotonic() + collection_deadline
    command_deadline_at = deadline_at - min(SNAPSHOT_WRITE_RESERVE_SECONDS, collection_deadline / 10)
    previous = load_previous_snapshot(snapshot_path)
    target: GatewayTarget | None = None

    try:
        completed = gateway_status_command(openclaw_command, command_deadline_at)
        if completed.returncode != 0:
            target = discover_node_host(openclaw_command, command_deadline_at)
            if target is not None:
                completed = gateway_status_command(openclaw_command, command_deadline_at, target)
    except CollectionDeadlineExceeded:
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
            ExitCode.COMMAND_TIMEOUT,
            "timeout",
        )
    except OSError:
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
            ExitCode.COMMAND_FAILED,
            "command_failed",
        )

    if completed.returncode != 0:
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
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
            ExitCode.MALFORMED_JSON,
            "malformed_json",
        )

    if not isinstance(status, dict):
        status = {}
    source = resolution_source(status, target.source if target else None)
    if source is None:
        return publish(
            snapshot_path,
            ExitCode.UNSUPPORTED_JSON,
            configuration_error_snapshot(previous, refresh_interval, status, target.source if target else None),
        )

    fleet_payload, agent_payload, task_payload, automation_payload = collect_metadata(
        openclaw_command,
        command_deadline_at,
        target,
    )
    try:
        secret = node_key_secret or load_node_key_secret()
    except OSError:
        secret = None
    fleet, agents, automations, automation_failure = sanitize_metadata(
        fleet_payload,
        agent_payload,
        task_payload,
        automation_payload,
        secret,
    )
    snapshot = build_current_snapshot(
        SCHEMA_VERSION,
        utc_now(),
        refresh_interval,
        source,
        fleet,
        agents,
        automations,
        automation_failure,
    )
    if fleet is None:
        retained = last_known_metadata(previous)
        if retained and retained.get("fleet", {}).get("available") is True:
            snapshot["lastKnown"] = retained
    fallback_url = target.url if target else None
    return publish_current(snapshot_path, snapshot, collected_target_url(status, fallback_url))


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
    parser.add_argument(
        "--automation-history",
        metavar="AUTOMATION_ID",
        help="open official read-only recent-run history for a collected Automation",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    snapshot_path = default_snapshot_path()
    if arguments.automation_history:
        return open_automation_history(
            snapshot_path,
            arguments.automation_history,
            ("openclaw",),
            OPENCLAW_TIMEOUT_MILLISECONDS,
            int(ExitCode.COMMAND_FAILED),
            load_previous_snapshot,
        )
    result = collect_gateway(snapshot_path, arguments.refresh_interval)
    json.dump(result.snapshot, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
