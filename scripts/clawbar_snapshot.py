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


def build_failure_snapshot(
    previous: dict[str, Any] | None,
    refresh_interval: int,
    failure_kind: str,
    schema_version: int,
    resolution_sources: Collection[str],
) -> dict[str, Any]:
    previous_failures = previous.get("consecutiveFailures", 0) if previous else 0
    failures = previous_failures + 1 if isinstance(previous_failures, int) else 1
    last_success = previous.get("lastSuccessAt") if previous else None
    has_last_success = isinstance(last_success, str)
    source = previous.get("resolutionSource") if previous else None
    if failures >= 2:
        state = "offline"
    elif has_last_success:
        state = "unstable"
    else:
        state = "unknown"
    return {
        "schemaVersion": schema_version,
        "generatedAt": utc_now(),
        "refreshIntervalSeconds": refresh_interval,
        "resolutionSource": source if source in resolution_sources else "unresolved",
        "gateway": {"state": state},
        "lastSuccessAt": last_success if has_last_success else None,
        "consecutiveFailures": failures,
        "failureKind": failure_kind,
    }


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
