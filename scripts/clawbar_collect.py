#!/usr/bin/env python3
"""Collect one structured OpenClaw Gateway status into Clawbar's cache."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, Sequence

if __package__:
    from .clawbar_automation import collect_automation_surface
    from .clawbar_gateway import (
        CollectionDeadlineExceeded,
        CommandOutputExceeded,
        GatewayTarget,
        automatic_resolution_missing,
        discover_node_host,
        gateway_status_command,
        resolution_source,
        retained_setup_candidates,
        run_command,
        seconds_until_deadline,
        selected_candidate,
        setup_required_snapshot,
        setup_retry_snapshot,
        setup_section,
    )
    from .clawbar_incidents import process_incident_transitions
    from .clawbar_metadata import (
        OUTPUT_EXCEEDED_LIMIT,
        build_current_snapshot,
        load_local_key_secret,
        sanitize_metadata,
    )
    from .clawbar_snapshot import (
        atomic_write_snapshot,
        build_failure_snapshot,
        last_known_metadata,
        load_snapshot,
        read_bounded_regular_file,
        utc_now,
    )
    from .clawbar_target_state import GatewayTargetState
else:
    from clawbar_automation import collect_automation_surface
    from clawbar_gateway import (
        CollectionDeadlineExceeded,
        CommandOutputExceeded,
        GatewayTarget,
        automatic_resolution_missing,
        discover_node_host,
        gateway_status_command,
        resolution_source,
        retained_setup_candidates,
        run_command,
        seconds_until_deadline,
        selected_candidate,
        setup_required_snapshot,
        setup_retry_snapshot,
        setup_section,
    )
    from clawbar_incidents import process_incident_transitions
    from clawbar_metadata import (
        OUTPUT_EXCEEDED_LIMIT,
        build_current_snapshot,
        load_local_key_secret,
        sanitize_metadata,
    )
    from clawbar_snapshot import (
        atomic_write_snapshot,
        build_failure_snapshot,
        last_known_metadata,
        load_snapshot,
        read_bounded_regular_file,
        utc_now,
    )
    from clawbar_target_state import GatewayTargetState

SCHEMA_VERSION = 1
DEFAULT_REFRESH_INTERVAL_SECONDS = 30
MIN_REFRESH_INTERVAL_SECONDS = 15
MAX_REFRESH_INTERVAL_SECONDS = 300
COLLECTION_DEADLINE_SECONDS = 12.0
SNAPSHOT_WRITE_RESERVE_SECONDS = 0.5
OPENCLAW_TIMEOUT_MILLISECONDS = 10_000
RESOLUTION_SOURCES = frozenset({"local", "configured_remote", "node_host", "tailscale"})


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






def default_snapshot_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "clawbar" / "snapshot.json"


def developer_demo_active() -> bool:
    runtime_directory = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_directory:
        return False
    try:
        marker = Path(runtime_directory) / "clawbar" / "demo-active"
        return read_bounded_regular_file(marker, 16).decode("utf-8").strip() == "1"
    except (OSError, UnicodeDecodeError):
        return False


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


def print_bounded_text_file(path: Path) -> ExitCode:
    try:
        content = read_bounded_regular_file(path).decode("utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return ExitCode.COMMAND_FAILED
    sys.stdout.write(content)
    return ExitCode.OK


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
) -> tuple[object | None, str | None]:
    try:
        return (
            decode_json(metadata_command(openclaw_command, arguments, deadline_at, target)),
            None,
        )
    except CommandOutputExceeded:
        return None, OUTPUT_EXCEEDED_LIMIT
    except (CollectionDeadlineExceeded, OSError):
        return None, None




METADATA_SURFACE_NAMES = ("fleet", "agents", "tasks")


def collect_metadata(
    openclaw_command: Sequence[str],
    deadline_at: float,
    target: GatewayTarget | None,
) -> tuple[object | None, object | None, object | None, object | None, dict[str, str | None]]:
    payloads: list[object | None] = []
    failures: dict[str, str | None] = {}
    for name, arguments in zip(METADATA_SURFACE_NAMES, METADATA_SURFACES):
        payload, failure = read_metadata_surface(openclaw_command, arguments, deadline_at, target)
        payloads.append(payload)
        failures[name] = failure

    def read_automation(arguments: Sequence[str]) -> object | None:
        payload, _ = read_metadata_surface(openclaw_command, arguments, deadline_at, target)
        return payload

    automation_payload = collect_automation_surface(read_automation)
    return (*payloads, automation_payload, failures)




def publish_current(
    snapshot_path: Path,
    snapshot: dict[str, Any],
    target: GatewayTarget | None,
) -> CollectionResult:
    target_state = GatewayTargetState(snapshot_path, SCHEMA_VERSION)
    if target is not None and target.source == "tailscale":
        target_state.record_verified_fallback(target.url)
    target_state.discard_legacy_current_target()
    return publish(snapshot_path, ExitCode.OK, snapshot)


def resolve_target(
    snapshot_path: Path,
    openclaw_command: Sequence[str],
    command_deadline_at: float,
    target: GatewayTarget | None,
) -> tuple[GatewayTarget | None, subprocess.CompletedProcess[str], bool]:
    """行き先決め: 選ばれた候補または自動解決でGateway応答を取得する。

    CollectionDeadlineExceeded と OSError は呼び出し側へそのまま伝わる。
    """
    automatic_setup_required = False
    if target is not None:
        completed = gateway_status_command(openclaw_command, command_deadline_at, target)
        return target, completed, automatic_setup_required
    completed = gateway_status_command(openclaw_command, command_deadline_at)
    if completed.returncode != 0:
        automatic_setup_required = automatic_resolution_missing(completed)
        target = discover_node_host(openclaw_command, command_deadline_at)
        if target is None:
            verified_url = GatewayTargetState(
                snapshot_path,
                SCHEMA_VERSION,
            ).load_verified_fallback()
            target = GatewayTarget(verified_url, "tailscale") if verified_url else None
        if target is not None:
            completed = gateway_status_command(openclaw_command, command_deadline_at, target)
    return target, completed, automatic_setup_required


def collect_gateway(
    snapshot_path: Path,
    refresh_interval: int,
    openclaw_command: Sequence[str] = ("openclaw",),
    collection_deadline: float = COLLECTION_DEADLINE_SECONDS,
    local_key_secret: bytes | None = None,
    candidate_key: str | None = None,
) -> CollectionResult:
    refresh_interval = validate_refresh_interval(refresh_interval)
    deadline_at = time.monotonic() + collection_deadline
    command_deadline_at = deadline_at - min(SNAPSHOT_WRITE_RESERVE_SECONDS, collection_deadline / 10)
    previous = load_previous_snapshot(snapshot_path)
    try:
        secret = local_key_secret or load_local_key_secret()
    except OSError:
        secret = None
    target = selected_candidate(snapshot_path, candidate_key, SCHEMA_VERSION) if candidate_key else None

    if candidate_key and target is None:
        return publish(
            snapshot_path,
            ExitCode.OK,
            setup_retry_snapshot(
                previous,
                refresh_interval,
                SCHEMA_VERSION,
                "candidate_not_found",
                "That Gateway candidate is no longer available. Refresh and choose a listed device.",
            ),
        )

    try:
        target, completed, automatic_setup_required = resolve_target(
            snapshot_path,
            openclaw_command,
            command_deadline_at,
            target,
        )
    except CollectionDeadlineExceeded:
        if candidate_key:
            return publish(
                snapshot_path,
                ExitCode.COMMAND_TIMEOUT,
                setup_retry_snapshot(
                    previous,
                    refresh_interval,
                    SCHEMA_VERSION,
                    "timeout",
                    "Gateway verification timed out. Check Tailscale and try again.",
                ),
            )
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
            ExitCode.COMMAND_TIMEOUT,
            "timeout",
        )
    except OSError:
        if candidate_key:
            return publish(
                snapshot_path,
                ExitCode.COMMAND_FAILED,
                setup_retry_snapshot(
                    previous,
                    refresh_interval,
                    SCHEMA_VERSION,
                    "candidate_unreachable",
                    "The selected device could not be verified. Check Tailscale or choose another device.",
                ),
            )
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
            ExitCode.COMMAND_FAILED,
            "command_failed",
        )

    if completed.returncode != 0:
        if target is not None and not candidate_key:
            return publish_failure(
                snapshot_path,
                previous,
                refresh_interval,
                ExitCode.COMMAND_FAILED,
                "command_failed",
            )
        if candidate_key:
            return publish(
                snapshot_path,
                ExitCode.OK,
                setup_retry_snapshot(
                    previous,
                    refresh_interval,
                    SCHEMA_VERSION,
                    "candidate_unreachable",
                    "The selected device could not be verified. Check Tailscale or choose another device.",
                ),
            )
        if automatic_setup_required and not (previous and isinstance(previous.get("lastSuccessAt"), str)):
            return publish(
                snapshot_path,
                ExitCode.OK,
                setup_required_snapshot(
                    snapshot_path,
                    previous,
                    refresh_interval,
                    command_deadline_at,
                    SCHEMA_VERSION,
                    secret,
                ),
            )
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
        if candidate_key:
            snapshot = configuration_error_snapshot(previous, refresh_interval, {}, None)
            snapshot["failureKind"] = "malformed_json"
            snapshot["setup"] = setup_section(
                retained_setup_candidates(previous),
                "The selected device does not provide a supported OpenClaw Gateway.",
            )
            return publish(snapshot_path, ExitCode.MALFORMED_JSON, snapshot)
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
        snapshot = configuration_error_snapshot(
            previous,
            refresh_interval,
            status,
            target.source if target else None,
        )
        if candidate_key:
            snapshot["setup"] = setup_section(
                retained_setup_candidates(previous),
                "The selected device does not provide a supported OpenClaw Gateway.",
            )
        return publish(snapshot_path, ExitCode.UNSUPPORTED_JSON, snapshot)

    fleet_payload, agent_payload, task_payload, automation_payload, metadata_failures = (
        collect_metadata(
            openclaw_command,
            command_deadline_at,
            target,
        )
    )
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
        metadata_failures=metadata_failures,
    )
    if fleet is None:
        retained = last_known_metadata(previous)
        if retained and retained.get("fleet", {}).get("available") is True:
            snapshot["lastKnown"] = retained
    return publish_current(snapshot_path, snapshot, target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"{__doc__} The whole collection exits within {int(COLLECTION_DEADLINE_SECONDS)} seconds."
    )
    parser.add_argument(
        "--read-cache",
        action="store_true",
        help="print the bounded regular snapshot cache without collecting",
    )
    parser.add_argument(
        "--read-theme-colors",
        type=Path,
        metavar="PATH",
        help="print one bounded regular UTF-8 theme colors file without collecting",
    )
    parser.add_argument(
        "--refresh-interval",
        default=DEFAULT_REFRESH_INTERVAL_SECONDS,
        type=parse_refresh_interval,
        metavar="SECONDS",
    )
    parser.add_argument(
        "--verify-candidate",
        metavar="CANDIDATE_KEY",
        help="verify one enumerated Tailscale candidate and collect from it",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    snapshot_path = default_snapshot_path()
    if arguments.read_theme_colors is not None:
        return int(print_bounded_text_file(arguments.read_theme_colors))
    if arguments.read_cache:
        snapshot = load_previous_snapshot(snapshot_path)
        if snapshot is None:
            return int(ExitCode.COMMAND_FAILED)
        json.dump(snapshot, sys.stdout, separators=(",", ":"), sort_keys=True)
        sys.stdout.write("\n")
        return int(ExitCode.OK)
    if developer_demo_active():
        snapshot = load_previous_snapshot(snapshot_path)
        if snapshot is not None:
            json.dump(snapshot, sys.stdout, separators=(",", ":"), sort_keys=True)
            sys.stdout.write("\n")
        return int(ExitCode.OK)
    result = collect_gateway(
        snapshot_path,
        arguments.refresh_interval,
        candidate_key=arguments.verify_candidate,
    )
    json.dump(result.snapshot, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
