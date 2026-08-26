"""Build and persist Clawbar snapshot state."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Collection

if __package__:
    from .clawbar_bounds import MAX_COLLECTION_BYTES
else:
    from clawbar_bounds import MAX_COLLECTION_BYTES


READ_CHUNK_BYTES = 64 * 1024
# 契約テストが参照する旧名。実体は clawbar_bounds.py に一元化済み。
MAX_STATE_FILE_BYTES = MAX_COLLECTION_BYTES


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def snapshot_envelope(
    schema_version: int,
    refresh_interval: int,
    resolution_source: str,
    gateway_state: str,
    last_success_at: str | None,
    consecutive_failures: int,
) -> dict[str, Any]:
    """失敗系snapshot共通の envelope。セクションとbarは各builderが加える。"""
    return {
        "schemaVersion": schema_version,
        "generatedAt": utc_now(),
        "refreshIntervalSeconds": refresh_interval,
        "resolutionSource": resolution_source,
        "gateway": {"state": gateway_state},
        "lastSuccessAt": last_success_at,
        "consecutiveFailures": consecutive_failures,
    }


def read_bounded_regular_file(path: Path, max_bytes: int = MAX_COLLECTION_BYTES) -> bytes:
    """Read one owner-controlled regular file without following its final link."""
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError(f"Refusing to read non-regular state file: {path}")
        if metadata.st_size > max_bytes:
            raise OSError(f"State file exceeds {max_bytes} bytes: {path}")
        content = bytearray()
        while len(content) <= max_bytes:
            chunk = os.read(
                descriptor,
                min(READ_CHUNK_BYTES, max_bytes + 1 - len(content)),
            )
            if not chunk:
                return bytes(content)
            content.extend(chunk)
        raise OSError(f"State file exceeds {max_bytes} bytes: {path}")
    finally:
        os.close(descriptor)


def load_snapshot(path: Path, schema_version: int) -> dict[str, Any] | None:
    try:
        raw = read_bounded_regular_file(path)
        value = json.loads(raw.decode("utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
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
    snapshot = snapshot_envelope(
        schema_version,
        refresh_interval,
        source if source in resolution_sources else "unresolved",
        state,
        last_success,
        failures,
    )
    snapshot["failureKind"] = failure_kind
    snapshot["fleet"] = {"available": False, "nodes": []}
    snapshot["agents"] = {"available": False, "items": []}
    snapshot["automations"] = {"available": False, "items": []}
    snapshot["bar"] = {
        "kind": "attention",
        "count": 0 if state == "no_data" else 1,
        "severity": "critical" if state == "offline" else "warning",
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
