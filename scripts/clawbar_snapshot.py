"""Own, read, and persist Clawbar's schema-version-1 Snapshot contract."""

from __future__ import annotations

import copy
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

if __package__:
    from .clawbar_bounds import MAX_COLLECTION_BYTES
else:
    from clawbar_bounds import MAX_COLLECTION_BYTES


SCHEMA_VERSION = 1
RESOLUTION_SOURCES = frozenset({"local", "configured_remote", "node_host", "tailscale"})
FAILURE_KINDS = frozenset(
    {
        "candidate_not_found",
        "candidate_unreachable",
        "command_failed",
        "malformed_json",
        "timeout",
        "unsupported_json",
    }
)
READ_CHUNK_BYTES = 64 * 1024
# 契約テストが参照する旧名。実体は clawbar_bounds.py に一元化済み。
MAX_STATE_FILE_BYTES = MAX_COLLECTION_BYTES


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _unavailable_sections() -> dict[str, dict[str, Any]]:
    return {
        "fleet": {"available": False, "nodes": []},
        "agents": {"available": False, "items": []},
        "automations": {"available": False, "items": []},
    }


def _bar(gateway_state: str, automation_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    automation_failures = sum(
        item.get("enabled") is True and item.get("lastResult") == "error"
        for item in (automation_items or [])
    )
    if gateway_state == "healthy":
        count = automation_failures
        severity = "critical" if count else "healthy"
    elif gateway_state == "degraded":
        count = automation_failures + 1
        severity = "critical" if automation_failures else "warning"
    elif gateway_state == "unstable":
        count, severity = 1, "warning"
    elif gateway_state in {"offline", "configuration_error"}:
        count, severity = 1, "critical"
    elif gateway_state in {"no_data", "setup_required"}:
        count, severity = 0, "warning"
    else:
        raise ValueError(f"Unsupported Gateway state: {gateway_state}")
    return {"kind": "attention" if count else "none", "count": count, "severity": severity}


def _last_known_metadata(previous: dict[str, Any] | None) -> dict[str, Any] | None:
    if not previous:
        return None
    retained = previous.get("lastKnown")
    if (
        isinstance(retained, dict)
        and isinstance(retained.get("observedAt"), str)
        and all(
            isinstance(retained.get(section), dict)
            for section in ("gateway", "fleet", "agents", "automations")
        )
    ):
        return copy.deepcopy(retained)
    observed_at = previous.get("lastSuccessAt")
    sections = {name: previous.get(name) for name in ("gateway", "fleet", "agents", "automations")}
    if not isinstance(observed_at, str) or not all(isinstance(value, dict) for value in sections.values()):
        return None
    return {"observedAt": observed_at, **copy.deepcopy(sections)}


def _complete_last_known(previous: dict[str, Any] | None) -> dict[str, Any] | None:
    retained = _last_known_metadata(previous)
    if retained is None:
        return None
    if all(retained[section].get("available") is True for section in ("fleet", "agents", "automations")):
        return retained
    return None


def _retained_setup_candidates(previous: dict[str, Any] | None) -> list[dict[str, str]]:
    setup = previous.get("setup") if previous else None
    candidates = setup.get("candidates") if isinstance(setup, dict) else None
    if not isinstance(candidates, list):
        return []
    return [
        {"key": candidate["key"], "name": candidate["name"]}
        for candidate in candidates
        if isinstance(candidate, dict)
        and isinstance(candidate.get("key"), str)
        and isinstance(candidate.get("name"), str)
    ]


@dataclass(frozen=True)
class SnapshotBuilder:
    previous: dict[str, Any] | None
    refresh_interval: int
    clock: Callable[[], str] = utc_now
    demo_scenario: str | None = None

    def _envelope(
        self,
        source: str | None,
        gateway_state: str,
        last_success_at: str | None,
        consecutive_failures: int,
    ) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "generatedAt": self.clock(),
            "refreshIntervalSeconds": self.refresh_interval,
            "resolutionSource": source if source in RESOLUTION_SOURCES else "unresolved",
            "gateway": {"state": gateway_state},
            "lastSuccessAt": last_success_at,
            "consecutiveFailures": consecutive_failures,
            **({"demoScenario": self.demo_scenario} if self.demo_scenario is not None else {}),
        }

    def current(
        self,
        source: str,
        fleet: list[dict[str, Any]] | None,
        agents: list[dict[str, Any]] | None,
        automations: list[dict[str, Any]] | None,
        automation_failure: str | None,
        metadata_failures: dict[str, str | None] | None,
    ) -> dict[str, Any]:
        degraded = fleet is None or agents is None or automations is None
        state = "degraded" if degraded else "healthy"
        generated_at = self.clock()
        failures = metadata_failures or {}
        fleet_section: dict[str, Any] = {"available": fleet is not None, "nodes": fleet or []}
        if fleet is None and failures.get("fleet"):
            fleet_section["reason"] = failures["fleet"]
        agents_section: dict[str, Any] = {"available": agents is not None, "items": agents or []}
        agents_failure = failures.get("agents") or failures.get("tasks")
        if agents is None and agents_failure:
            agents_section["reason"] = agents_failure
        automation_items = automations or []
        automation_section: dict[str, Any] = {
            "available": automations is not None,
            "items": automation_items,
        }
        if automation_failure is not None:
            automation_section["reason"] = automation_failure
        retained = _complete_last_known(self.previous) if degraded else None
        return {
            "schemaVersion": SCHEMA_VERSION,
            "generatedAt": generated_at,
            "refreshIntervalSeconds": self.refresh_interval,
            "resolutionSource": source if source in RESOLUTION_SOURCES else "unresolved",
            "gateway": {"state": state},
            "fleet": fleet_section,
            "agents": agents_section,
            "automations": automation_section,
            "bar": _bar(state, automation_items),
            "lastSuccessAt": generated_at,
            "consecutiveFailures": 0,
            **({"demoScenario": self.demo_scenario} if self.demo_scenario is not None else {}),
            **({"lastKnown": retained} if retained is not None else {}),
        }

    def failure(self, failure_kind: str) -> dict[str, Any]:
        _require_failure_kind(failure_kind)
        previous_failures = self.previous.get("consecutiveFailures", 0) if self.previous else 0
        failures = previous_failures + 1 if isinstance(previous_failures, int) else 1
        retained = _last_known_metadata(self.previous)
        previous_success = self.previous.get("lastSuccessAt") if self.previous else None
        last_success = retained.get("observedAt") if retained else previous_success
        if not isinstance(last_success, str):
            last_success = None
        state = "no_data" if last_success is None else ("offline" if failures >= 2 else "unstable")
        source = self.previous.get("resolutionSource") if self.previous else None
        return {
            **self._envelope(source, state, last_success, failures),
            **_unavailable_sections(),
            "bar": _bar(state),
            "failureKind": failure_kind,
            **({"lastKnown": retained} if retained is not None else {}),
        }

    def setup(
        self,
        candidates: list[dict[str, str]] | None,
        guidance: str,
        error: str | None = None,
        failure_kind: str | None = None,
    ) -> dict[str, Any]:
        if failure_kind is not None:
            _require_failure_kind(failure_kind)
        public_candidates = copy.deepcopy(candidates) if candidates is not None else _retained_setup_candidates(self.previous)
        setup: dict[str, Any] = {"candidates": public_candidates, "guidance": guidance}
        if error is not None:
            setup["error"] = error
        retained = _last_known_metadata(self.previous)
        return {
            **self._envelope(None, "setup_required", None, 0),
            **_unavailable_sections(),
            "bar": _bar("setup_required"),
            "setup": setup,
            **({"failureKind": failure_kind} if failure_kind is not None else {}),
            **({"lastKnown": retained} if retained is not None else {}),
        }

    def configuration_error(
        self,
        source: str | None,
        failure_kind: str,
        setup: tuple[list[dict[str, str]] | None, str, str | None] | None = None,
    ) -> dict[str, Any]:
        _require_failure_kind(failure_kind)
        retained = _last_known_metadata(self.previous)
        previous_success = self.previous.get("lastSuccessAt") if self.previous else None
        last_success = previous_success if isinstance(previous_success, str) else None
        setup_section = None
        if setup is not None:
            candidates, guidance, error = setup
            public_candidates = candidates if candidates is not None else _retained_setup_candidates(self.previous)
            setup_section = {
                "candidates": copy.deepcopy(public_candidates),
                "guidance": guidance,
                **({"error": error} if error is not None else {}),
            }
        return {
            **self._envelope(source, "configuration_error", last_success, 0),
            **_unavailable_sections(),
            "bar": _bar("configuration_error"),
            "failureKind": failure_kind,
            **({"setup": setup_section} if setup_section is not None else {}),
            **({"lastKnown": retained} if retained is not None else {}),
        }


def _require_failure_kind(failure_kind: str) -> None:
    if failure_kind not in FAILURE_KINDS:
        raise ValueError(f"Unsupported failure kind: {failure_kind}")


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
            chunk = os.read(descriptor, min(READ_CHUNK_BYTES, max_bytes + 1 - len(content)))
            if not chunk:
                return bytes(content)
            content.extend(chunk)
        raise OSError(f"State file exceeds {max_bytes} bytes: {path}")
    finally:
        os.close(descriptor)


def read_json_document(path: Path) -> dict[str, Any] | None:
    try:
        raw = read_bounded_regular_file(path)
        value = json.loads(raw.decode("utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


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
