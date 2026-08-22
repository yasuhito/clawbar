#!/usr/bin/env python3
"""Publish fictional snapshots for Clawbar development and review."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

if __package__:
    from .clawbar_collect import default_snapshot_path
    from .clawbar_incidents import process_incident_transitions
    from .clawbar_snapshot import atomic_write_snapshot
else:
    from clawbar_collect import default_snapshot_path
    from clawbar_incidents import process_incident_transitions
    from clawbar_snapshot import atomic_write_snapshot


def demo_marker_path() -> Path:
    runtime_directory = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_directory:
        raise RuntimeError("XDG_RUNTIME_DIR is required for the developer demonstration")
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
            ["omarchy-shell", "-q", "shell", "rescanPlugins"],
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass

SCENARIOS = (
    "setup-required",
    "healthy",
    "working-agents",
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


def timestamp(now: datetime, *, seconds: int = 0) -> str:
    return (
        now + timedelta(seconds=seconds)
    ).isoformat(timespec="milliseconds").replace("+00:00", "Z")


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


def working_agents(now: datetime) -> list[dict[str, Any]]:
    return [
        {
            "key": "agent:demo-planner",
            "name": "Planner",
            "activity": "working",
            "model": "Fictional model",
            "taskResult": {"state": "failed", "completedAt": timestamp(now, seconds=-540)},
        },
        {
            "key": "agent:demo-builder",
            "name": "Builder",
            "activity": "waiting",
            "model": "Fictional model",
            "taskResult": {"state": "none"},
        },
        {
            "key": "agent:demo-observer",
            "name": "Observer",
            "activity": "idle",
            "taskResult": {"state": "succeeded", "completedAt": timestamp(now, seconds=-240)},
        },
    ]


def healthy_snapshot(now: datetime) -> dict[str, Any]:
    generated_at = timestamp(now)
    return {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "refreshIntervalSeconds": 30,
        "resolutionSource": "local",
        "gateway": {"state": "healthy"},
        "fleet": {
            "available": True,
            "nodes": [
                node("local", "Local", "healthy", generated_at),
                node("studio", "Studio", "healthy", generated_at),
                node("archive", "Archive", "healthy", generated_at),
            ],
        },
        "agents": {"available": True, "items": []},
        "automations": {
            "available": True,
            "items": [
                automation("morning", "Morning review", now),
                automation("archive", "Weekly archive", now, enabled=False),
            ],
        },
        "bar": {"kind": "working_agents", "count": 0, "severity": "healthy"},
        "lastSuccessAt": generated_at,
        "consecutiveFailures": 0,
    }


def historical(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "observedAt": snapshot["lastSuccessAt"],
        "gateway": snapshot["gateway"],
        "fleet": snapshot["fleet"],
        "agents": snapshot["agents"],
        "automations": snapshot["automations"],
    }


def snapshot_for(scenario: str, now: datetime) -> dict[str, Any]:
    snapshot = healthy_snapshot(now)
    if scenario == "setup-required":
        snapshot.update({
            "resolutionSource": "unresolved",
            "gateway": {"state": "setup_required"},
            "fleet": {"available": False, "nodes": []},
            "agents": {"available": False, "items": []},
            "automations": {"available": False, "items": []},
            "bar": {"kind": "attention", "count": 0, "severity": "warning"},
            "lastSuccessAt": None,
            "setup": {
                "candidates": [
                    {"key": "candidate:65a84e5cbb06f1195fb3", "name": "gateway-alpha"},
                    {"key": "candidate:9d487cbecf592db688fb", "name": "gateway-beta"},
                ],
                "guidance": "Choose a Tailscale device to verify as your OpenClaw Gateway.",
            },
        })
    elif scenario == "working-agents":
        snapshot["agents"]["items"] = working_agents(now)
        snapshot["bar"] = {"kind": "working_agents", "count": 1, "severity": "healthy"}
    elif scenario in {"unstable-gateway", "offline-gateway"}:
        previous = copy.deepcopy(snapshot)
        state = "unstable" if scenario == "unstable-gateway" else "offline"
        snapshot.update({
            "gateway": {"state": state},
            "fleet": {"available": False, "nodes": []},
            "agents": {"available": False, "items": []},
            "automations": {"available": False, "items": []},
            "bar": {
                "kind": "attention",
                "count": 1,
                "severity": "warning" if state == "unstable" else "critical",
            },
            "consecutiveFailures": 1 if state == "unstable" else 2,
            "failureKind": "command_failed",
            "lastKnown": historical(previous),
        })
    elif scenario == "degraded-gateway":
        snapshot["gateway"] = {"state": "degraded"}
        snapshot["automations"] = {"available": False, "items": [], "reason": "unavailable"}
        snapshot["bar"] = {"kind": "attention", "count": 1, "severity": "warning"}
    elif scenario == "configuration-error":
        snapshot.update({
            "resolutionSource": "configured_remote",
            "gateway": {"state": "configuration_error"},
            "fleet": {"available": False, "nodes": []},
            "agents": {"available": False, "items": []},
            "automations": {"available": False, "items": []},
            "bar": {"kind": "attention", "count": 1, "severity": "critical"},
            "failureKind": "unsupported_json",
        })
    elif scenario == "automation-failure":
        snapshot["automations"]["items"][0] = automation(
            "morning", "Morning review", now, result="error", failures=3
        )
        snapshot["bar"] = {"kind": "attention", "count": 1, "severity": "critical"}
    elif scenario == "stale-snapshot":
        stale_at = now - timedelta(seconds=121)
        snapshot = healthy_snapshot(stale_at)
    elif scenario == "empty-fleet":
        snapshot["fleet"] = {"available": True, "nodes": []}
    elif scenario == "grouped-incidents":
        snapshot["agents"]["items"] = working_agents(now)
        observed_at = snapshot["generatedAt"]
        snapshot["fleet"]["nodes"][1] = node("studio", "Studio", "offline", observed_at)
        snapshot["fleet"]["nodes"][2] = node("archive", "Archive", "offline", observed_at)
        snapshot["automations"]["items"][0] = automation(
            "morning", "Morning review", now, result="error", failures=3
        )
        snapshot["bar"] = {"kind": "attention", "count": 3, "severity": "critical"}
    elif scenario not in {"healthy", "recovery"}:
        raise ValueError(f"Unknown scenario: {scenario}")
    snapshot["demoScenario"] = scenario
    return snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", nargs="?", choices=SCENARIOS)
    parser.add_argument("--snapshot", type=Path, help="override the XDG state snapshot path")
    parser.add_argument("--resume", action="store_true", help="resume normal scheduled collection")
    parser.add_argument("--list-scenarios", action="store_true", help="list available fictional scenarios")
    return parser

def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.list_scenarios:
        if arguments.scenario or arguments.resume:
            parser.error("--list-scenarios does not accept another action")
        print("\n".join(SCENARIOS))
        return 0
    if arguments.resume:
        if arguments.scenario:
            parser.error("--resume does not accept a scenario")
        set_demo_active(False)
        reset_demo_incidents()
        reload_shell()
        return 0
    if not arguments.scenario:
        parser.error("a scenario is required unless --resume or --list-scenarios is used")
    set_demo_active(True)
    reload_shell()
    snapshot = snapshot_for(arguments.scenario, datetime.now(timezone.utc))
    snapshot_path = arguments.snapshot or default_snapshot_path()
    atomic_write_snapshot(snapshot_path, snapshot)
    process_demo_incidents(snapshot)
    reload_shell()
    json.dump(snapshot, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
