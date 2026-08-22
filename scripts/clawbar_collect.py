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
    from .clawbar_automation import (
        collect_automation_surface,
        collected_target_url,
        open_automation_history,
        target_state_path,
    )
    from .clawbar_gateway import (
        CollectionDeadlineExceeded,
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
        stored_target,
        verified_target_path,
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
    from clawbar_gateway import (
        CollectionDeadlineExceeded,
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
        stored_target,
        verified_target_path,
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
        return marker.read_text(encoding="utf-8").strip() == "1"
    except OSError:
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
    status: dict[str, Any],
    target: GatewayTarget | None,
) -> CollectionResult:
    target_url = collected_target_url(status, target.url if target else None)
    if target_url is None:
        return publish(snapshot_path, ExitCode.OK, snapshot)
    atomic_write_snapshot(
        target_state_path(snapshot_path),
        {
            "schemaVersion": SCHEMA_VERSION,
            "snapshotGeneratedAt": snapshot["generatedAt"],
            "source": snapshot["resolutionSource"],
            "url": target_url,
        },
    )
    if target is not None and target.source == "tailscale":
        atomic_write_snapshot(
            verified_target_path(snapshot_path),
            {
                "schemaVersion": SCHEMA_VERSION,
                "source": "tailscale",
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
    candidate_key: str | None = None,
) -> CollectionResult:
    refresh_interval = validate_refresh_interval(refresh_interval)
    deadline_at = time.monotonic() + collection_deadline
    command_deadline_at = deadline_at - min(SNAPSHOT_WRITE_RESERVE_SECONDS, collection_deadline / 10)
    previous = load_previous_snapshot(snapshot_path)
    target = selected_candidate(snapshot_path, candidate_key, SCHEMA_VERSION) if candidate_key else None
    automatic_setup_required = False

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
        if target is not None:
            completed = gateway_status_command(openclaw_command, command_deadline_at, target)
        else:
            completed = gateway_status_command(openclaw_command, command_deadline_at)
            if completed.returncode != 0:
                automatic_setup_required = automatic_resolution_missing(completed)
                target = discover_node_host(openclaw_command, command_deadline_at)
                if target is None:
                    target = stored_target(verified_target_path(snapshot_path), "tailscale", SCHEMA_VERSION)
                if target is not None:
                    completed = gateway_status_command(openclaw_command, command_deadline_at, target)
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
        if automatic_setup_required:
            return publish(
                snapshot_path,
                ExitCode.OK,
                setup_required_snapshot(
                    snapshot_path,
                    previous,
                    refresh_interval,
                    command_deadline_at,
                    SCHEMA_VERSION,
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
    return publish_current(snapshot_path, snapshot, status, target)


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
    parser.add_argument(
        "--verify-candidate",
        metavar="CANDIDATE_KEY",
        help="verify one enumerated Tailscale candidate and collect from it",
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
