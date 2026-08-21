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


def load_node_key_secret() -> bytes:
    """Return the local secret used to pseudonymize private Node ids."""
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
            return secret_path.read_bytes()
        with os.fdopen(descriptor, "wb") as output:
            output.write(secret)
    if len(secret) != _SECRET_BYTES:
        raise OSError("Invalid Clawbar Node key secret")
    return secret


def bounded_text(value: object, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    value = value.strip()
    return value[:80] if value else fallback


def timestamp_from_milliseconds(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def opaque_node_key(node_id: object, secret: bytes) -> str | None:
    node_id = bounded_text(node_id)
    if not node_id:
        return None
    digest = hmac.new(secret, node_id.encode("utf-8"), hashlib.sha256).hexdigest()[:20]
    return f"node:{digest}"


def sanitize_fleet(payload: object, node_key_secret: bytes | None) -> list[dict[str, Any]] | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
        return None
    fleet = []
    for raw in payload["nodes"][:100]:
        if not isinstance(raw, dict):
            continue
        key = opaque_node_key(raw.get("nodeId"), node_key_secret) if node_key_secret is not None else None
        node = {
            "name": bounded_text(raw.get("displayName"), "Unnamed Node"),
            "state": "healthy" if raw.get("connected") is True else "offline",
        }
        if key is not None:
            node["key"] = key
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


def sanitize_metadata(
    fleet_payload: object,
    agent_payload: object,
    task_payload: object,
    node_key_secret: bytes | None,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
    return (
        sanitize_fleet(fleet_payload, node_key_secret),
        sanitize_agents(agent_payload, task_payload),
    )
