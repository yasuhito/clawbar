cd /home/yasuhito/Work/clawbar && python3 - <<'PY'
import json
import subprocess
import sys

AUTOMATION_IDS = (
    "2fc98fc3-38cb-4e32-92b6-cbb10b39272d",
    "bdfdc4fd-3325-4fc9-9038-da99beba7a01",
)


def cleanup_finished_automation_tabs():
    try:
        terminals_payload = json.loads(
            subprocess.check_output(["orca-ide", "terminal", "list", "--json"], text=True)
        )
        terminals = (terminals_payload.get("result") or {}).get("terminals") or []
        finished_tab_ids = set()
        for automation_id in AUTOMATION_IDS:
            runs_payload = json.loads(
                subprocess.check_output(
                    ["orca-ide", "automations", "runs", "--id", automation_id, "--json"],
                    text=True,
                )
            )
            for run in (runs_payload.get("result") or {}).get("runs") or []:
                if run.get("status") not in {"completed", "failed", "cancelled", "timed_out"}:
                    continue
                tab_id = run.get("terminalSessionId")
                if tab_id:
                    finished_tab_ids.add(tab_id)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return

    for terminal in terminals:
        if terminal.get("tabId") not in finished_tab_ids:
            continue
        handle = terminal.get("handle")
        if not handle:
            continue
        subprocess.run(
            ["orca-ide", "terminal", "close", "--terminal", handle, "--tab", "--json"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


cleanup_finished_automation_tabs()

repo = "yasuhito/clawbar"


def gh_json(*args):
    return json.loads(subprocess.check_output(["gh", *args], text=True))

prs = gh_json(
    "pr", "list", "-R", repo, "--state", "open", "--label", "agent:review", "--limit", "100",
    "--json", "number,isDraft,labels,statusCheckRollup,reviewRequests"
)

blocked_labels = {"agent:reviewing", "ready-for-human", "agent:blocked"}
# 同時実行は 1 件だけ。別の PR をレビュー中（agent:reviewing がある）なら新しい run を起こさない。
if any("agent:reviewing" in {label["name"] for label in pr.get("labels", [])} for pr in prs):
    sys.exit(1)
for pr in prs:
    labels = {label["name"] for label in pr.get("labels", [])}
    if labels & blocked_labels:
        continue
    if pr.get("isDraft"):
        sys.exit(0)

    requests = pr.get("reviewRequests") or []
    copilot_requested = False
    for request in requests:
        login = (request.get("login") or (request.get("requestedReviewer") or {}).get("login") or "").lower()
        if "copilot" in login:
            copilot_requested = True
            break
    if copilot_requested:
        continue

    checks = pr.get("statusCheckRollup") or []
    check_pending = False
    for check in checks:
        status = (check.get("status") or check.get("state") or "").upper()
        if status in {"QUEUED", "IN_PROGRESS", "PENDING", "EXPECTED", "WAITING"}:
            check_pending = True
            break
    if check_pending:
        continue

    sys.exit(0)

sys.exit(1)
PY
