"""Read bounded Automation metadata."""

from __future__ import annotations

from typing import Callable

if __package__:
    from .clawbar_bounds import MAX_METADATA_ITEMS
else:
    from clawbar_bounds import MAX_METADATA_ITEMS

ReadPage = Callable[[dict[str, object]], object | None]


def collect_automation_surface(read_page: ReadPage) -> object | None:
    """cron.list を includeDisabled 付きでページ送りし、上限内なら全 job を返す。"""
    jobs: list[object] = []
    offset = 0
    while True:
        limit = min(200, MAX_METADATA_ITEMS + 1 - len(jobs))
        payload = read_page({"includeDisabled": True, "limit": limit, "offset": offset})
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            return None
        total = payload.get("total")
        if isinstance(total, int) and not isinstance(total, bool) and total > MAX_METADATA_ITEMS:
            return {"jobs": [], "total": total}
        jobs.extend(payload["jobs"])
        if len(jobs) > MAX_METADATA_ITEMS:
            return {"jobs": jobs}
        if payload.get("hasMore") is not True:
            return {"jobs": jobs, "total": total}
        next_offset = payload.get("nextOffset")
        if not isinstance(next_offset, int) or isinstance(next_offset, bool) or next_offset <= offset:
            return None
        if len(jobs) == MAX_METADATA_ITEMS:
            return {"jobs": [], "total": MAX_METADATA_ITEMS + 1}
        offset = next_offset
