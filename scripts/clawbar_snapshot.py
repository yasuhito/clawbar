"""Build and persist Clawbar snapshot state."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Collection


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def load_snapshot(path: Path, schema_version: int) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("schemaVersion") != schema_version:
        return None
    return value


def last_known_metadata(previous: dict[str, Any] | None) -> dict[str, Any] | None:
    if not previous:
        return None
    retained = previous.get("lastKnown")
    if (
        isinstance(retained, dict)
        and isinstance(retained.get("observedAt"), str)
        and all(isinstance(retained.get(section), dict) for section in ("gateway", "fleet", "agents", "automations"))
    ):
        return retained
    observed_at = previous.get("lastSuccessAt")
    gateway = previous.get("gateway")
    fleet = previous.get("fleet")
    agents = previous.get("agents")
    automations = previous.get("automations")
    if (
        not isinstance(observed_at, str)
        or not isinstance(gateway, dict)
        or not isinstance(fleet, dict)
        or not isinstance(agents, dict)
        or not isinstance(automations, dict)
    ):
        return None
    return {
        "observedAt": observed_at,
        "gateway": gateway,
        "fleet": fleet,
        "agents": agents,
        "automations": automations,
    }


def build_failure_snapshot(
    previous: dict[str, Any] | None,
    refresh_interval: int,
    failure_kind: str,
    schema_version: int,
    resolution_sources: Collection[str],
) -> dict[str, Any]:
    previous_failures = previous.get("consecutiveFailures", 0) if previous else 0
    failures = previous_failures + 1 if isinstance(previous_failures, int) else 1
    retained = last_known_metadata(previous)
    previous_success = previous.get("lastSuccessAt") if previous else None
    last_success = retained.get("observedAt") if retained else previous_success
    if not isinstance(last_success, str):
        last_success = None
    source = previous.get("resolutionSource") if previous else None
    if last_success is None:
        state = "no_data"
    elif failures >= 2:
        state = "offline"
    else:
        state = "unstable"
    snapshot = {
        "schemaVersion": schema_version,
        "generatedAt": utc_now(),
        "refreshIntervalSeconds": refresh_interval,
        "resolutionSource": source if source in resolution_sources else "unresolved",
        "gateway": {"state": state},
        "fleet": {"available": False, "nodes": []},
        "agents": {"available": False, "items": []},
        "automations": {"available": False, "items": []},
        "bar": {
            "kind": "attention",
            "count": 0 if state == "no_data" else 1,
            "severity": "critical" if state == "offline" else "warning",
        },
        "lastSuccessAt": last_success,
        "consecutiveFailures": failures,
        "failureKind": failure_kind,
    }
    if retained is not None:
        snapshot["lastKnown"] = retained
    return snapshot


def atomic_write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            json.dump(snapshot, temporary, separators=(",", ":"), sort_keys=True)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
