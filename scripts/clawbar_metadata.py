"""Reduce Gateway metadata to Clawbar's privacy-safe snapshot contract."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECRET_BYTES = 32
MAX_NODE_REGISTRATIONS = 5_000
MAX_AUTOMATIONS = 500
AUTOMATION_KINDS = frozenset({"at", "every", "cron", "on-exit"})
AUTOMATION_RESULTS = frozenset({"ok", "error", "skipped"})



def load_local_key_secret() -> bytes:
    """Return the local secret used to pseudonymize private identifiers."""
    runtime_home = os.environ.get("XDG_RUNTIME_DIR")
    state_home = os.environ.get("XDG_STATE_HOME")
    if runtime_home:
        secret_root = Path(runtime_home)
    elif state_home:
        secret_root = Path(state_home)
    else:
        secret_root = Path.home() / ".local" / "state"
    secret_path = secret_root / "clawbar" / "node-key-secret"
    secret_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        secret = secret_path.read_bytes()
    except FileNotFoundError:
        secret = secrets.token_bytes(_SECRET_BYTES)
        try:
            descriptor = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            secret = secret_path.read_bytes()
        else:
            with os.fdopen(descriptor, "wb") as output:
                output.write(secret)
    if len(secret) != _SECRET_BYTES:
        raise OSError("Invalid Clawbar local key secret")
    return secret


def bounded_text(value: object, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    value = value.strip()
    return value[:80] if value else fallback


def positive_milliseconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return 0.0
    return float(value)


def timestamp_from_milliseconds(value: object) -> str | None:
    milliseconds = positive_milliseconds(value)
    if not milliseconds:
        return None
    try:
        return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def _opaque_key(message: str, secret: bytes, prefix: str) -> str:
    digest = hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()[:20]
    return f"{prefix}:{digest}"


def opaque_candidate_key(device_id: str, secret: bytes) -> str:
    return _opaque_key(f"tailscale-candidate\0{device_id}", secret, "candidate")


def opaque_node_key(node_id: object, secret: bytes) -> str | None:
    node_id = bounded_text(node_id)
    if not node_id:
        return None
    return _opaque_key(node_id, secret, "node")


def merge_richer_node_details(target: dict[str, Any], source: dict[str, Any]) -> None:
    current_model = bounded_text(target.get("modelIdentifier"))
    candidate_model = bounded_text(source.get("modelIdentifier"))
    if not current_model and candidate_model:
        target["modelIdentifier"] = candidate_model

    current_platform = bounded_text(target.get("platform"))
    candidate_platform = bounded_text(source.get("platform"))
    if not candidate_platform:
        return
    generic_platforms = {"darwin", "linux", "macos", "win32", "windows"}
    current_family = current_platform.casefold()
    candidate_family = candidate_platform.casefold()
    compatible = candidate_family.startswith(current_family)
    if current_family == "darwin":
        compatible = candidate_family.startswith(("darwin", "macos"))
    elif current_family == "win32":
        compatible = candidate_family.startswith(("win32", "windows"))
    if not current_platform or (
        current_family in generic_platforms
        and compatible
        and len(candidate_platform) > len(current_platform)
    ):
        target["platform"] = candidate_platform


def freshest_node_registrations(
    nodes: list[object],
    secret: bytes,
) -> list[tuple[str, str, dict[str, Any]]] | None:
    selected: dict[
        str,
        tuple[tuple[bool, float, str], tuple[str, str, dict[str, Any]]],
    ] = {}
    order: list[str] = []
    for raw in nodes[:MAX_NODE_REGISTRATIONS]:
        if not isinstance(raw, dict):
            continue
        registration_key = opaque_node_key(raw.get("nodeId"), secret)
        if registration_key is None:
            return None
        display_name = bounded_text(raw.get("displayName"))
        name = display_name or "Unnamed Node"
        identity = display_name.casefold() if display_name else registration_key
        key = (
            _opaque_key(f"node-display-name\0{identity}", secret, "node")
            if display_name
            else registration_key
        )
        preference = (
            raw.get("connected") is True,
            positive_milliseconds(raw.get("lastSeenAtMs")),
            registration_key,
        )
        candidate = dict(raw)
        current = selected.get(identity)
        if current is not None and current[0] >= preference:
            merge_richer_node_details(current[1][2], candidate)
            continue
        if current is None:
            order.append(identity)
        else:
            merge_richer_node_details(candidate, current[1][2])
        selected[identity] = (preference, (key, name, candidate))
    return [selected[identity][1] for identity in order[:100]]


def sanitize_fleet(payload: object, node_key_secret: bytes | None) -> list[dict[str, Any]] | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
        return None
    if not payload["nodes"]:
        return []
    if node_key_secret is None:
        return None
    selected = freshest_node_registrations(payload["nodes"], node_key_secret)
    if selected is None:
        return None

    fleet = []
    for key, name, raw in selected:
        node = {
            "key": key,
            "name": name,
            "state": "healthy" if raw.get("connected") is True else "offline",
        }
        for source_key, output_key in (("platform", "platform"), ("modelIdentifier", "model"), ("version", "version")):
            value = bounded_text(raw.get(source_key))
            if value:
                node[output_key] = value
        last_seen = timestamp_from_milliseconds(raw.get("lastSeenAtMs"))
        if last_seen:
            node["lastSeenAt"] = last_seen
        fleet.append(node)
    return fleet


def task_timestamp(task: dict[str, Any]) -> float:
    for key in ("endedAt", "updatedAt", "startedAt", "createdAt"):
        value = task.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return 0


def sanitize_agents(agent_payload: object, task_payload: object) -> list[dict[str, Any]] | None:
    if not isinstance(agent_payload, dict) or not isinstance(agent_payload.get("agents"), list):
        return None
    if not isinstance(task_payload, dict) or not isinstance(task_payload.get("tasks"), list):
        return None
    tasks = [task for task in task_payload["tasks"][:500] if isinstance(task, dict)]
    agents = []
    for raw in agent_payload["agents"][:100]:
        if not isinstance(raw, dict):
            continue
        agent_id = bounded_text(raw.get("id"))
        if not agent_id:
            continue
        own_tasks = sorted(
            (task for task in tasks if task.get("agentId") == agent_id),
            key=task_timestamp,
            reverse=True,
        )
        statuses = [task.get("status") for task in own_tasks]
        activity = "working" if "running" in statuses else "waiting" if "queued" in statuses else "idle"
        completed = next(
            (task for task in own_tasks if task.get("status") in {"completed", "failed", "timed_out", "cancelled"}),
            None,
        )
        result: dict[str, Any] = {"state": "none"}
        if completed is not None:
            result["state"] = "succeeded" if completed.get("status") == "completed" else "failed"
            completed_at = timestamp_from_milliseconds(completed.get("endedAt") or completed.get("updatedAt"))
            if completed_at:
                result["completedAt"] = completed_at
        agent = {
            "key": f"agent:{agent_id}",
            "name": agent_id,
            "activity": activity,
            "taskResult": result,
        }
        model = bounded_text(raw.get("model"))
        if model:
            agent["model"] = model
        agents.append(agent)
    return agents

def sanitize_automations(payload: object) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        return None, "unavailable"
    total = payload.get("total")
    if isinstance(total, int) and not isinstance(total, bool) and total > MAX_AUTOMATIONS:
        return None, "more_than_500"
    raw_jobs = payload["jobs"]
    if len(raw_jobs) > MAX_AUTOMATIONS:
        return None, "more_than_500"

    automations = []
    seen_ids: set[str] = set()
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            return None, "unavailable"
        automation_id = raw.get("id")
        if not isinstance(automation_id, str) or not automation_id or len(automation_id) > 512:
            return None, "unavailable"
        if automation_id in seen_ids:
            return None, "unavailable"
        seen_ids.add(automation_id)

        schedule = raw.get("schedule")
        state = raw.get("state")
        if not isinstance(schedule, dict) or not isinstance(state, dict):
            return None, "unavailable"
        kind = schedule.get("kind")
        if kind not in AUTOMATION_KINDS:
            return None, "unavailable"
        result = state.get("lastRunStatus", state.get("lastStatus"))
        if result not in AUTOMATION_RESULTS:
            result = "none"
        consecutive_failures = state.get("consecutiveErrors", 0)
        if (
            isinstance(consecutive_failures, bool)
            or not isinstance(consecutive_failures, int)
            or consecutive_failures < 0
        ):
            consecutive_failures = 0

        automations.append({
            "id": automation_id,
            "name": bounded_text(raw.get("name"), "Unnamed Automation"),
            "enabled": raw.get("enabled") is True,
            "kind": kind,
            "nextRunAt": timestamp_from_milliseconds(state.get("nextRunAtMs")),
            "lastRunAt": timestamp_from_milliseconds(state.get("lastRunAtMs")),
            "lastResult": result,
            "consecutiveFailures": consecutive_failures,
        })

    def sort_key(automation: dict[str, Any]) -> tuple[object, ...]:
        if automation["enabled"] and automation["lastResult"] == "error":
            return (0, automation["name"].casefold(), automation["id"])
        if automation["enabled"] and automation["nextRunAt"] is not None:
            return (1, automation["nextRunAt"], automation["name"].casefold(), automation["id"])
        if automation["enabled"]:
            return (2, automation["name"].casefold(), automation["id"])
        return (3, automation["name"].casefold(), automation["id"])

    automations.sort(key=sort_key)
    return automations, None




def sanitize_metadata(
    fleet_payload: object,
    agent_payload: object,
    task_payload: object,
    automation_payload: object,
    node_key_secret: bytes | None,
) -> tuple[
    list[dict[str, Any]] | None,
    list[dict[str, Any]] | None,
    list[dict[str, Any]] | None,
    str | None,
]:
    automations, automation_failure = sanitize_automations(automation_payload)
    return (
        sanitize_fleet(fleet_payload, node_key_secret),
        sanitize_agents(agent_payload, task_payload),
        automations,
        automation_failure,
    )


def build_current_snapshot(
    schema_version: int,
    generated_at: str,
    refresh_interval: int,
    source: str,
    fleet: list[dict[str, Any]] | None,
    agents: list[dict[str, Any]] | None,
    automations: list[dict[str, Any]] | None,
    automation_failure: str | None,
) -> dict[str, Any]:
    degraded = fleet is None or agents is None or automations is None
    gateway_state = "degraded" if degraded else "healthy"
    automation_items = automations or []
    critical_items = sum(node.get("state") == "offline" for node in (fleet or []))
    critical_items += sum(
        automation.get("enabled") is True and automation.get("lastResult") == "error"
        for automation in automation_items
    )
    attention_items = critical_items + (1 if degraded else 0)
    working_agents = sum(agent.get("activity") == "working" for agent in (agents or []))
    if critical_items:
        bar = {"kind": "attention", "count": attention_items, "severity": "critical"}
    elif attention_items:
        bar = {"kind": "attention", "count": attention_items, "severity": "warning"}
    else:
        bar = {"kind": "working_agents", "count": working_agents, "severity": "healthy"}
    automation_section: dict[str, Any] = {
        "available": automations is not None,
        "items": automation_items,
    }
    if automation_failure is not None:
        automation_section["reason"] = automation_failure
    return {
        "schemaVersion": schema_version,
        "generatedAt": generated_at,
        "refreshIntervalSeconds": refresh_interval,
        "resolutionSource": source,
        "gateway": {"state": gateway_state},
        "fleet": {"available": fleet is not None, "nodes": fleet or []},
        "agents": {"available": agents is not None, "items": agents or []},
        "automations": automation_section,
        "bar": bar,
        "lastSuccessAt": generated_at,
        "consecutiveFailures": 0,
    }
