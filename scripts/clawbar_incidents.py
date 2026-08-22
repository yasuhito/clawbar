"""Track per-login Incident transitions and emit privacy-safe notifications."""

from __future__ import annotations

import fcntl
import os
import subprocess
from pathlib import Path
from typing import Any

if __package__:
    from .clawbar_snapshot import atomic_write_snapshot, load_snapshot
else:
    from clawbar_snapshot import atomic_write_snapshot, load_snapshot

INCIDENT_STATE_SCHEMA_VERSION = 1
NOTIFICATION_TIMEOUT_SECONDS = 0.25


def default_incident_state_path() -> Path | None:
    runtime_directory = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_directory:
        return None
    return Path(runtime_directory) / "clawbar" / "incidents.json"


def valid_incidents(state: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    if state is None or not isinstance(state.get("incidents"), dict):
        return {}
    incidents: dict[str, dict[str, str]] = {}
    for key, value in state["incidents"].items():
        if (
            isinstance(key, str)
            and isinstance(value, dict)
            and isinstance(value.get("label"), str)
            and isinstance(value.get("state"), str)
        ):
            incidents[key] = {"label": value["label"], "state": value["state"]}
    return incidents


def reconcile_incidents(
    snapshot: dict[str, Any],
    previous: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    incidents = valid_incidents(previous)
    starts: list[dict[str, str]] = []
    recoveries: list[dict[str, str]] = []

    def start(key: str, label: str, state: str) -> None:
        incident = {"label": label, "state": state}
        if key not in incidents:
            starts.append(incident)
        incidents[key] = incident

    def recover(key: str, label: str) -> None:
        if key in incidents:
            incidents.pop(key)
            recoveries.append({"label": label, "state": "Recovered"})

    gateway = snapshot.get("gateway")
    gateway_state = gateway.get("state") if isinstance(gateway, dict) else None
    if gateway_state == "offline":
        start("gateway", "Gateway", "Offline")
    elif gateway_state == "configuration_error":
        start("gateway", "Gateway", "Configuration error")
    elif gateway_state in {"healthy", "degraded"}:
        recover("gateway", "Gateway")
    elif gateway_state in {"no_data", "setup_required"}:
        incidents.clear()

    fleet = snapshot.get("fleet")
    if isinstance(fleet, dict) and fleet.get("available") is True and isinstance(fleet.get("nodes"), list):
        observed_nodes: set[str] = set()
        for node in fleet["nodes"]:
            if not isinstance(node, dict):
                continue
            key = node.get("key")
            label = node.get("name")
            if not isinstance(key, str) or not isinstance(label, str):
                continue
            incident_key = f"node:{key}"
            observed_nodes.add(incident_key)
            if node.get("state") == "offline":
                start(incident_key, label, "Offline")
            else:
                recover(incident_key, label)
        for key in tuple(incidents):
            if key.startswith("node:") and key not in observed_nodes:
                incidents.pop(key)

    automations = snapshot.get("automations")
    if (
        isinstance(automations, dict)
        and automations.get("available") is True
        and isinstance(automations.get("items"), list)
    ):
        observed_automations: set[str] = set()
        for automation in automations["items"]:
            if not isinstance(automation, dict):
                continue
            automation_id = automation.get("id")
            label = automation.get("name")
            if not isinstance(automation_id, str) or not isinstance(label, str):
                continue
            incident_key = f"automation:{automation_id}"
            observed_automations.add(incident_key)
            if automation.get("enabled") is True and automation.get("lastResult") == "error":
                start(incident_key, label, "Automation failure")
            elif automation.get("enabled") is True:
                recover(incident_key, label)
            else:
                incidents.pop(incident_key, None)
        for key in tuple(incidents):
            if key.startswith("automation:") and key not in observed_automations:
                incidents.pop(key)

    state = {"schemaVersion": INCIDENT_STATE_SCHEMA_VERSION, "incidents": incidents}
    return state, starts, recoveries


def notification_arguments(changes: list[dict[str, str]], *, recovered: bool) -> list[str]:
    count = len(changes)
    noun = "Incident" if count == 1 else "Incidents"
    action = "recovered" if recovered else "started"
    urgency = "normal" if recovered else "critical"
    body_parts = [f"{change['label']}: {change['state']}" for change in changes[:3]]
    if count > 3:
        body_parts.append(f"+{count - 3} more")
    return [
        "--app-name=Clawbar",
        f"--urgency={urgency}",
        f"Clawbar: {'' if count == 1 else f'{count} '}{noun} {action}",
        "; ".join(body_parts),
    ]


def dispatch_notification(changes: list[dict[str, str]], *, recovered: bool) -> None:
    if not changes:
        return
    try:
        subprocess.run(
            ["notify-send", *notification_arguments(changes, recovered=recovered)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=NOTIFICATION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def process_incident_transitions(snapshot: dict[str, Any]) -> None:
    state_path = default_incident_state_path()
    if state_path is None:
        return
    try:
        state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_descriptor = os.open(state_path.with_suffix(".lock"), os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(lock_descriptor, "r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            previous = load_snapshot(state_path, INCIDENT_STATE_SCHEMA_VERSION)
            state, starts, recoveries = reconcile_incidents(snapshot, previous)
            atomic_write_snapshot(state_path, state)
            dispatch_notification(starts, recovered=False)
            dispatch_notification(recoveries, recovered=True)
    except OSError:
        return
