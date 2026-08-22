"""Read bounded Automation metadata and open official run history."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

if __package__:
    from .clawbar_target_state import GatewayTargetState
else:
    from clawbar_target_state import GatewayTargetState

ReadSurface = Callable[[Sequence[str]], object | None]
LoadSnapshot = Callable[[Path], dict[str, Any] | None]


def collect_automation_surface(read_surface: ReadSurface) -> object | None:
    jobs: list[object] = []
    offset = 0
    while True:
        limit = min(200, 501 - len(jobs))
        params = {"includeDisabled": True, "limit": limit, "offset": offset}
        payload = read_surface((
            "gateway",
            "call",
            "cron.list",
            "--params",
            json.dumps(params, separators=(",", ":"), sort_keys=True),
            "--json",
        ))
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            return None
        total = payload.get("total")
        if isinstance(total, int) and not isinstance(total, bool) and total > 500:
            return {"jobs": [], "total": total}
        jobs.extend(payload["jobs"])
        if len(jobs) > 500:
            return {"jobs": jobs}
        if payload.get("hasMore") is not True:
            return {"jobs": jobs, "total": total}
        next_offset = payload.get("nextOffset")
        if not isinstance(next_offset, int) or isinstance(next_offset, bool) or next_offset <= offset:
            return None
        if len(jobs) == 500:
            return {"jobs": [], "total": 501}
        offset = next_offset






def open_automation_history(
    snapshot_path: Path,
    automation_id: str,
    openclaw_command: Sequence[str],
    timeout_milliseconds: int,
    command_failed_code: int,
    schema_version: int,
    load_snapshot: LoadSnapshot,
) -> int:
    snapshot = load_snapshot(snapshot_path)
    automations = snapshot.get("automations") if snapshot else None
    items = automations.get("items") if isinstance(automations, dict) and automations.get("available") else None
    target_url = (
        GatewayTargetState(snapshot_path, schema_version).current_url(snapshot.get("generatedAt"))
        if snapshot
        else None
    )
    known_id = isinstance(items, list) and any(
        isinstance(item, dict) and item.get("id") == automation_id for item in items
    )
    if not known_id or target_url is None:
        print("Automation history unavailable", file=sys.stderr)
        return command_failed_code
    try:
        completed = subprocess.run(
            [
                *openclaw_command,
                "cron",
                "runs",
                "--id",
                automation_id,
                "--limit",
                "50",
                "--url",
                target_url,
                "--timeout",
                str(timeout_milliseconds),
            ],
            check=False,
        )
    except OSError:
        print("Automation history unavailable", file=sys.stderr)
        return command_failed_code
    return completed.returncode
