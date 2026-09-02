#!/usr/bin/env python3
"""Publish fictional Snapshots for Clawbar development and review."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

if __package__:
    from .clawbar_collect import default_snapshot_path
    from .clawbar_gateway import SETUP_GUIDANCE
    from .clawbar_incidents import process_incident_transitions
    from .clawbar_snapshot import SnapshotBuilder, atomic_write_snapshot
else:
    from clawbar_collect import default_snapshot_path
    from clawbar_gateway import SETUP_GUIDANCE
    from clawbar_incidents import process_incident_transitions
    from clawbar_snapshot import SnapshotBuilder, atomic_write_snapshot


SCENARIOS = (
    "setup-required",
    "healthy",
    "registered-agents",
    "unstable-gateway",
    "offline-gateway",
    "degraded-gateway",
    "configuration-error",
    "automation-failure",
    "stale-snapshot",
    "empty-fleet",
    "grouped-incidents",
    "recovery",
)
FIXTURE_NOW = datetime(2026, 8, 24, 17, 44, tzinfo=UTC)


def demo_marker_path() -> Path:
    runtime_directory = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_directory:
        raise RuntimeError(
            "XDG_RUNTIME_DIR is required for the developer demonstration"
        )
    return Path(runtime_directory) / "clawbar" / "demo-active"


def set_demo_active(active: bool) -> None:
    marker = demo_marker_path()
    marker.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    marker.write_text("1\n" if active else "0\n", encoding="utf-8")


def demo_incident_runtime() -> Path:
    return Path(os.environ["XDG_RUNTIME_DIR"]) / "clawbar-demo"


def process_demo_incidents(snapshot: dict[str, Any]) -> None:
    runtime_directory = os.environ["XDG_RUNTIME_DIR"]
    os.environ["XDG_RUNTIME_DIR"] = str(demo_incident_runtime())
    try:
        process_incident_transitions(snapshot)
    finally:
        os.environ["XDG_RUNTIME_DIR"] = runtime_directory


def reset_demo_incidents() -> None:
    state_directory = demo_incident_runtime() / "clawbar"
    for name in ("incidents.json", "incidents.lock"):
        (state_directory / name).unlink(missing_ok=True)


def reload_shell() -> None:
    if os.environ.get("CLAWBAR_DEMO_NO_RESCAN") == "1":
        return
    try:
        subprocess.run(
            ["omarchy-shell", "-q", "shell", "rescanPlugins"], check=False, timeout=2
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def timestamp(now: datetime, *, seconds: int = 0) -> str:
    return (
        (now + timedelta(seconds=seconds))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def node(key: str, name: str, state: str, observed_at: str) -> dict[str, Any]:
    return {
        "key": f"node:demo-{key}",
        "name": name,
        "state": state,
        "platform": "Linux",
        "model": "Fictional workstation",
        "version": "2026.7.1-2",
        "lastSeenAt": observed_at,
    }


def automation(
    automation_id: str,
    name: str,
    now: datetime,
    *,
    enabled: bool = True,
    result: str = "ok",
    failures: int = 0,
) -> dict[str, Any]:
    return {
        "id": f"demo-{automation_id}",
        "name": name,
        "enabled": enabled,
        "kind": "cron",
        "nextRunAt": timestamp(now, seconds=900) if enabled else None,
        "lastRunAt": timestamp(now, seconds=-240),
        "lastResult": result,
        "consecutiveFailures": failures,
    }


def registered_agents(now: datetime) -> list[dict[str, Any]]:
    return [
        {
            "key": "agent:demo-planner",
            "name": "Planner",
            "model": "Fictional model",
            "taskResult": {
                "state": "failed",
                "completedAt": timestamp(now, seconds=-540),
            },
        },
        {
            "key": "agent:demo-builder",
            "name": "Builder",
            "model": "Fictional model",
            "taskResult": {"state": "none"},
        },
        {
            "key": "agent:demo-observer",
            "name": "Observer",
            "taskResult": {
                "state": "succeeded",
                "completedAt": timestamp(now, seconds=-240),
            },
        },
    ]


def demo_metadata(
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    observed_at = timestamp(now)
    fleet = [
        node("local", "Local", "healthy", observed_at),
        node("studio", "Studio", "healthy", observed_at),
        node("archive", "Archive", "healthy", observed_at),
    ]
    automations = [
        automation("morning", "Morning review", now),
        automation("archive", "Weekly archive", now, enabled=False),
    ]
    return fleet, [], automations


def current_demo(
    scenario: str | None,
    now: datetime,
    *,
    previous: dict[str, Any] | None = None,
    fleet: list[dict[str, Any]] | None = None,
    agents: list[dict[str, Any]] | None = None,
    automations: list[dict[str, Any]] | None = None,
    automation_failure: str | None = None,
) -> dict[str, Any]:
    default_fleet, default_agents, default_automations = demo_metadata(now)
    return SnapshotBuilder(
        previous,
        30,
        clock=lambda: timestamp(now),
        demo_scenario=scenario,
    ).current(
        "local",
        default_fleet if fleet is None else fleet,
        default_agents if agents is None else agents,
        default_automations if automations is None else automations,
        automation_failure,
        {},
    )


def snapshot_for(scenario: str, now: datetime) -> dict[str, Any]:
    healthy = current_demo(None, now)
    fleet, agents, automations = demo_metadata(now)
    builder = SnapshotBuilder(
        healthy, 30, clock=lambda: timestamp(now), demo_scenario=scenario
    )

    if scenario == "setup-required":
        candidates = [
            {"key": "candidate:65a84e5cbb06f1195fb3", "name": "gateway-alpha"},
            {"key": "candidate:9d487cbecf592db688fb", "name": "gateway-beta"},
        ]
        return SnapshotBuilder(
            None,
            30,
            clock=lambda: timestamp(now),
            demo_scenario=scenario,
        ).setup(candidates, SETUP_GUIDANCE)
    if scenario == "healthy":
        return current_demo(scenario, now)
    if scenario == "registered-agents":
        return current_demo(scenario, now, agents=registered_agents(now))
    if scenario == "unstable-gateway":
        return builder.failure("command_failed")
    if scenario == "offline-gateway":
        unstable = SnapshotBuilder(healthy, 30, clock=lambda: timestamp(now)).failure(
            "command_failed"
        )
        return SnapshotBuilder(
            unstable,
            30,
            clock=lambda: timestamp(now),
            demo_scenario=scenario,
        ).failure("command_failed")
    if scenario == "degraded-gateway":
        return builder.current("local", fleet, agents, None, "unavailable", {})
    if scenario == "configuration-error":
        return SnapshotBuilder(
            None,
            30,
            clock=lambda: timestamp(now),
            demo_scenario=scenario,
        ).configuration_error("configured_remote", "unsupported_json")
    if scenario == "automation-failure":
        failing = [
            automation("morning", "Morning review", now, result="error", failures=3),
            automations[1],
        ]
        return builder.current("local", fleet, agents, failing, None, {})
    if scenario == "stale-snapshot":
        stale_at = now - timedelta(seconds=121)
        return current_demo(scenario, stale_at)
    if scenario == "empty-fleet":
        return builder.current("local", [], agents, automations, None, {})
    if scenario == "grouped-incidents":
        fleet[1] = node("studio", "Studio", "offline", timestamp(now))
        fleet[2] = node("archive", "Archive", "offline", timestamp(now))
        failing = [
            automation("morning", "Morning review", now, result="error", failures=3),
            automation("nightly", "Nightly sync", now, result="error", failures=2),
            automations[1],
        ]
        return builder.current(
            "local", fleet, registered_agents(now), failing, None, {}
        )
    if scenario == "recovery":
        recovered = [
            automations[0],
            automation("nightly", "Nightly sync", now),
            automations[1],
        ]
        return builder.current("local", fleet, agents, recovered, None, {})
    raise ValueError(f"Unknown scenario: {scenario}")


def fixture_snapshots() -> dict[str, dict[str, Any]]:
    return {scenario: snapshot_for(scenario, FIXTURE_NOW) for scenario in SCENARIOS}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", nargs="?", choices=SCENARIOS)
    parser.add_argument(
        "--snapshot", type=Path, help="override the XDG state snapshot path"
    )
    parser.add_argument(
        "--resume", action="store_true", help="resume normal scheduled collection"
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="list available fictional scenarios",
    )
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="print all scenarios using a fixed clock",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    actions = sum(
        bool(value)
        for value in (
            arguments.scenario,
            arguments.resume,
            arguments.list_scenarios,
            arguments.fixtures,
        )
    )
    if actions != 1:
        parser.error(
            "choose exactly one scenario, --resume, --list-scenarios, or --fixtures"
        )
    if arguments.fixtures:
        json.dump(fixture_snapshots(), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    if arguments.list_scenarios:
        print("\n".join(SCENARIOS))
        return 0
    if arguments.resume:
        set_demo_active(False)
        reset_demo_incidents()
        reload_shell()
        return 0

    set_demo_active(True)
    reload_shell()
    snapshot = snapshot_for(arguments.scenario, datetime.now(UTC))
    snapshot_path = arguments.snapshot or default_snapshot_path()
    atomic_write_snapshot(snapshot_path, snapshot)
    process_demo_incidents(snapshot)
    reload_shell()
    json.dump(snapshot, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
