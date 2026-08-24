"""Read bounded Automation metadata."""

from __future__ import annotations

import json
from typing import Callable, Sequence

ReadSurface = Callable[[Sequence[str]], object | None]


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
