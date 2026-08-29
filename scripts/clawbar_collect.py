#!/usr/bin/env python3
"""Collect one structured OpenClaw Gateway status into Clawbar's cache."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Sequence

if __package__:
    from . import clawbar_snapshot as snapshot_contract
    from .clawbar_automation import collect_automation_surface
    from .clawbar_commands import (
        CollectionDeadlineExceeded,
        CommandOutputExceeded,
        CommandResult,
        GatewayCommandSurface,
        SubprocessCommandSurface,
    )
    from .clawbar_gateway import (
        SETUP_GUIDANCE,
        GatewayTarget,
        automatic_resolution_missing,
        discover_node_host,
        resolution_source,
        selected_candidate,
        setup_required_snapshot,
        setup_retry_snapshot,
    )
    from .clawbar_incidents import process_incident_transitions
    from .clawbar_metadata import OUTPUT_EXCEEDED_LIMIT, load_local_key_secret, sanitize_metadata
    from .clawbar_snapshot import (
        SnapshotBuilder,
        atomic_write_snapshot,
        read_bounded_regular_file,
        read_json_document,
    )
    from .clawbar_target_state import GatewayTargetState
else:
    import clawbar_snapshot as snapshot_contract
    from clawbar_automation import collect_automation_surface
    from clawbar_commands import (
        CollectionDeadlineExceeded,
        CommandOutputExceeded,
        CommandResult,
        GatewayCommandSurface,
        SubprocessCommandSurface,
    )
    from clawbar_gateway import (
        SETUP_GUIDANCE,
        GatewayTarget,
        automatic_resolution_missing,
        discover_node_host,
        resolution_source,
        selected_candidate,
        setup_required_snapshot,
        setup_retry_snapshot,
    )
    from clawbar_incidents import process_incident_transitions
    from clawbar_metadata import OUTPUT_EXCEEDED_LIMIT, load_local_key_secret, sanitize_metadata
    from clawbar_snapshot import (
        SnapshotBuilder,
        atomic_write_snapshot,
        read_bounded_regular_file,
        read_json_document,
    )
    from clawbar_target_state import GatewayTargetState

DEFAULT_REFRESH_INTERVAL_SECONDS = 30
MIN_REFRESH_INTERVAL_SECONDS = 15
MAX_REFRESH_INTERVAL_SECONDS = 300
COLLECTION_DEADLINE_SECONDS = 12.0
SNAPSHOT_WRITE_RESERVE_SECONDS = 0.5


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


CANDIDATE_NOT_FOUND_GUIDANCE = (
    "That Gateway candidate is no longer available. Refresh and choose a listed device."
)
CANDIDATE_TIMEOUT_GUIDANCE = (
    "Gateway verification timed out. Check Tailscale and try again."
)
CANDIDATE_UNREACHABLE_GUIDANCE = (
    "The selected device could not be verified. Check Tailscale or choose another device."
)
CANDIDATE_UNSUPPORTED_GUIDANCE = (
    "The selected device does not provide a supported OpenClaw Gateway."
)

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
    snapshot = read_json_document(path)
    if snapshot is None or snapshot.get("schemaVersion") != snapshot_contract.SCHEMA_VERSION:
        return None
    return snapshot


def print_bounded_text_file(path: Path) -> ExitCode:
    try:
        content = read_bounded_regular_file(path).decode("utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return ExitCode.COMMAND_FAILED
    sys.stdout.write(content)
    return ExitCode.OK


def configuration_error_source(
    previous: dict[str, Any] | None,
    status: dict[str, Any],
    source_hint: str | None,
) -> str | None:
    source = resolution_source(status, source_hint)
    if source is not None:
        return source
    previous_source = previous.get("resolutionSource") if previous else None
    return previous_source if previous_source in snapshot_contract.RESOLUTION_SOURCES else None



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
        SnapshotBuilder(previous, refresh_interval).failure(failure_kind),
    )





def decode_json(completed: CommandResult) -> object | None:
    if completed.returncode != 0:
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None

def read_metadata_surface(ask: Callable[[], CommandResult]) -> tuple[object | None, str | None]:
    """1 つの metadata 質問を投げ、(payload, 失敗理由) を返す。失敗は Degraded Gateway に留める。"""
    try:
        return decode_json(ask()), None
    except CommandOutputExceeded:
        return None, OUTPUT_EXCEEDED_LIMIT
    except (CollectionDeadlineExceeded, OSError):
        return None, None


def collect_metadata(
    commands: GatewayCommandSurface,
    deadline_at: float,
    target: GatewayTarget | None,
) -> tuple[object | None, object | None, object | None, object | None, dict[str, str | None]]:
    url = target.url if target is not None else None
    surfaces: tuple[tuple[str, Callable[[], CommandResult]], ...] = (
        ("fleet", lambda: commands.nodes_status(deadline_at, url)),
        ("agents", lambda: commands.agents_list(deadline_at, url)),
        ("tasks", lambda: commands.tasks_list(deadline_at, url)),
    )
    payloads: list[object | None] = []
    failures: dict[str, str | None] = {}
    for name, ask in surfaces:
        payload, failure = read_metadata_surface(ask)
        payloads.append(payload)
        failures[name] = failure

    def read_automation_page(params: dict[str, object]) -> object | None:
        payload, _ = read_metadata_surface(lambda: commands.cron_list(deadline_at, url, params))
        return payload

    automation_payload = collect_automation_surface(read_automation_page)
    return (*payloads, automation_payload, failures)




def publish_current(
    snapshot_path: Path,
    snapshot: dict[str, Any],
    target: GatewayTarget | None,
) -> CollectionResult:
    target_state = GatewayTargetState(snapshot_path)
    if target is not None and target.source == "tailscale":
        target_state.record_verified_fallback(target.url)
    target_state.discard_legacy_current_target()
    return publish(snapshot_path, ExitCode.OK, snapshot)


def candidate_retry(
    snapshot_path: Path,
    previous: dict[str, Any] | None,
    refresh_interval: int,
    failure_kind: str,
    guidance: str,
    exit_code: ExitCode = ExitCode.OK,
) -> CollectionResult:
    """候補確かめ: 検証に失敗した候補モードの分岐。再選択を促して終了する。"""
    return publish(
        snapshot_path,
        exit_code,
        setup_retry_snapshot(
            SnapshotBuilder(previous, refresh_interval),
            failure_kind,
            guidance,
        ),
    )


def resolve_target(
    snapshot_path: Path,
    commands: GatewayCommandSurface,
    command_deadline_at: float,
    target: GatewayTarget | None,
) -> tuple[GatewayTarget | None, CommandResult, bool]:
    """行き先決め: 選ばれた候補または自動解決でGateway応答を取得する。

    CollectionDeadlineExceeded と OSError は呼び出し側へそのまま伝わる。
    """
    automatic_setup_required = False
    if target is not None:
        completed = commands.gateway_status(command_deadline_at, target.url)
        return target, completed, automatic_setup_required
    completed = commands.gateway_status(command_deadline_at)
    if completed.returncode != 0:
        automatic_setup_required = automatic_resolution_missing(completed)
        target = discover_node_host(commands, command_deadline_at)
        if target is None:
            verified_url = GatewayTargetState(snapshot_path).load_verified_fallback()
            target = GatewayTarget(verified_url, "tailscale") if verified_url else None
        if target is not None:
            completed = commands.gateway_status(command_deadline_at, target.url)
    return target, completed, automatic_setup_required


def decode_status_or_fail(
    snapshot_path: Path,
    previous: dict[str, Any] | None,
    refresh_interval: int,
    candidate_key: str | None,
    target: GatewayTarget | None,
    completed: CommandResult,
) -> CollectionResult | tuple[dict[str, Any], str | None]:
    """答え読み取り: Gateway応答を解読し source を判定する。

    戻り値は CollectionResult ならここで確定（呼び出し側は即 return）。
    (status, source) なら収集へ続行する。
    """
    builder = SnapshotBuilder(previous, refresh_interval)
    try:
        status = json.loads(completed.stdout)
    except json.JSONDecodeError:
        if candidate_key:
            setup = (None, SETUP_GUIDANCE, CANDIDATE_UNSUPPORTED_GUIDANCE)
            snapshot = builder.configuration_error(None, "malformed_json", setup)
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
        setup = (None, SETUP_GUIDANCE, CANDIDATE_UNSUPPORTED_GUIDANCE) if candidate_key else None
        snapshot = builder.configuration_error(
            configuration_error_source(previous, status, target.source if target else None),
            "unsupported_json",
            setup,
        )
        return publish(snapshot_path, ExitCode.UNSUPPORTED_JSON, snapshot)
    return status, source


def collect_gateway(
    snapshot_path: Path,
    refresh_interval: int,
    *,
    commands: GatewayCommandSurface,
    collection_deadline: float = COLLECTION_DEADLINE_SECONDS,
    local_key_secret: bytes | None = None,
    candidate_key: str | None = None,
) -> CollectionResult:
    """1 回の収集。外部 CLI へは commands（Gateway Command Surface）だけを通して話す。"""
    refresh_interval = validate_refresh_interval(refresh_interval)
    deadline_at = time.monotonic() + collection_deadline
    command_deadline_at = deadline_at - min(SNAPSHOT_WRITE_RESERVE_SECONDS, collection_deadline / 10)
    previous = load_previous_snapshot(snapshot_path)
    try:
        secret = local_key_secret or load_local_key_secret()
    except OSError:
        secret = None
    target = selected_candidate(snapshot_path, candidate_key) if candidate_key else None

    if candidate_key and target is None:
        return candidate_retry(
            snapshot_path,
            previous,
            refresh_interval,
            "candidate_not_found",
            CANDIDATE_NOT_FOUND_GUIDANCE,
        )

    try:
        target, completed, automatic_setup_required = resolve_target(
            snapshot_path,
            commands,
            command_deadline_at,
            target,
        )
    except CollectionDeadlineExceeded:
        if candidate_key:
            return candidate_retry(
                snapshot_path,
                previous,
                refresh_interval,
                "timeout",
                CANDIDATE_TIMEOUT_GUIDANCE,
                exit_code=ExitCode.COMMAND_TIMEOUT,
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
            return candidate_retry(
                snapshot_path,
                previous,
                refresh_interval,
                "candidate_unreachable",
                CANDIDATE_UNREACHABLE_GUIDANCE,
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
            return candidate_retry(
                snapshot_path,
                previous,
                refresh_interval,
                "candidate_unreachable",
                CANDIDATE_UNREACHABLE_GUIDANCE,
            )
        if automatic_setup_required and not (previous and isinstance(previous.get("lastSuccessAt"), str)):
            return publish(
                snapshot_path,
                ExitCode.OK,
                setup_required_snapshot(
                    snapshot_path,
                    SnapshotBuilder(previous, refresh_interval),
                    command_deadline_at,
                    secret,
                    commands,
                ),
            )
        return publish_failure(
            snapshot_path,
            previous,
            refresh_interval,
            ExitCode.COMMAND_FAILED,
            "command_failed",
        )

    decoded = decode_status_or_fail(
        snapshot_path,
        previous,
        refresh_interval,
        candidate_key,
        target,
        completed,
    )
    if isinstance(decoded, CollectionResult):
        return decoded
    status, source = decoded

    fleet_payload, agent_payload, task_payload, automation_payload, metadata_failures = (
        collect_metadata(
            commands,
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
    snapshot = SnapshotBuilder(previous, refresh_interval).current(
        source,
        fleet,
        agents,
        automations,
        automation_failure,
        metadata_failures,
    )
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
        commands=SubprocessCommandSurface(),
        candidate_key=arguments.verify_candidate,
    )
    json.dump(result.snapshot, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
