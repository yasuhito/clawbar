# Bug triage

A consolidated list of code-supported defects and product inconsistencies raised by the feature documents. Confirmed fixes carry a **Status** line and a Beads issue. Open questions about focus, layout, contrast, screen-reader behavior, timing, and user preference remain in their source documents until hand verification supplies evidence. This list lets the product team decide whether to fix, document as intended, or leave each behavior.

## Summary

The documents raised six distinct code-supported concerns after verification-only questions were excluded and duplicate symptoms were merged. There are no high-severity entries. B-01 and B-02 are fixed together: user-requested refresh now has bounded progress and failure feedback while scheduled collection remains quiet. Four medium concerns remain around fallback management, Incident transitions, notification reliability, and retained state after removal.

| ID | Title | Severity | Area | Decision needed | Issue |
| --- | --- | --- | --- | --- | --- |
| B-01 | Manual refresh has no progress indication when a Snapshot is already loaded | medium | bar | fixed | clawbar-8w3.20 |
| B-02 | Scheduler-service failure is invisible when old data remains loaded | medium | bar | fixed | clawbar-8w3.20 |
| B-03 | A verified fallback Gateway cannot be forgotten or replaced in Clawbar | medium | setup | product call | — |
| B-04 | Removing or disabling a failing target silently ends Incident monitoring | medium | notifications | product call | — |
| B-05 | Failed notification delivery permanently consumes the transition | medium | notifications | fix | — |
| B-06 | Plugin removal has no cleanup path for persisted Clawbar state | medium | lifecycle/privacy | product call | — |

## High

No high-severity code-supported defects were found during drafting.

## Medium

### B-01: Manual refresh has no progress indication when a Snapshot is already loaded

- **Status:** Fixed and verified in the running Omarchy panel by `clawbar-8w3.20`. User-requested refresh prefixes the summary with `Refreshing…`, animates the Claw, and preserves existing rows; scheduled collection remains quiet.

- **Where the user meets it:** The user presses `r` or middle-clicks while current or old data is visible.
- **What happens / what was expected:** Collection starts, but the bar and panel continue to look idle until a different result arrives. Two identical results make the action appear to do nothing. A common manual action should either show bounded progress or explicitly choose and document silent refresh.
- **Reproduce:** 1. Load a Healthy Snapshot. 2. Delay the Gateway response for 8 seconds. 3. Open the panel and press `r`. 4. Observe the bar and panel before completion.
- **Why (from the code):** `Clawbar.qml:83-90` changes visible state to `collecting` only when `lastSnapshot === null`; otherwise it calls the service without publishing busy state. `ClawbarService.qml:18-32` exposes candidate verification but not ordinary collector-running state to the widget.
- **Severity:** `medium`. The action remains safe and eventually settles, but a common user request gives no acknowledgement.
- **Decision needed:** `product call`. Add a subtle refreshing state/label, or explicitly accept silent background refresh and explain that choice.
- **Raised by:** [Manual refresh](bar/manual-refresh.md#open-questions-and-verification), [Surface and actions](foundations/surface-and-actions.md#while-waiting), [Bar signal and tooltip](bar/signal-and-tooltip.md#waiting-begins).

### B-02: Scheduler-service failure is invisible when old data remains loaded

- **Status:** Fixed and verified in the running Omarchy panel by `clawbar-8w3.20`. Failure preserves the existing Snapshot and shows `Refresh failed · showing last known` for six seconds.

- **Where the user meets it:** The Clawbar widget is present but its scheduler service cannot be resolved, and the user manually refreshes while an old Snapshot is loaded.
- **What happens / what was expected:** The request fails immediately, the old state remains unchanged, and only the shell console gets a warning. The user expects an in-panel indication that refresh could not start.
- **Reproduce:** 1. Load a Healthy Snapshot. 2. Run the widget without a matching service entry. 3. Press `r` or middle-click. 4. Compare panel and shell console.
- **Why (from the code):** `Clawbar.qml:83-87` logs `Clawbar scheduler service unavailable`; it sets `no_data` only when `lastSnapshot === null` and returns without any visible error when old data exists.
- **Severity:** `medium`. Failure is recoverable by fixing/reloading the plugin, but the UI silently presents old status after an explicit refresh request.
- **Decision needed:** `fix`. Surface a private-safe unavailable/refresh-failed message while preserving the old Snapshot as historical context.
- **Raised by:** [Manual refresh](bar/manual-refresh.md#open-questions-and-verification), [Gateway health and Last Known state](gateway/health-and-last-known-state.md#open-questions-and-verification), [Collection and freshness](foundations/collection-and-freshness.md#open-questions-and-verification).

### B-03: A verified fallback Gateway cannot be forgotten or replaced in Clawbar

- **Where the user meets it:** A Tailscale fallback was verified, but the user later wants a different fallback while automatic OpenClaw resolution remains unavailable.
- **What happens / what was expected:** Clawbar silently reuses the stored target and no longer exposes candidate setup. There is no Clawbar action to forget it or return to candidate selection.
- **Reproduce:** 1. Enter Gateway Setup Required. 2. Verify a supported candidate. 3. Keep automatic routes unresolved. 4. Open the panel and try to choose another fallback without editing files.
- **Why (from the code):** `scripts/clawbar_target_state.py:20-44` provides record and load operations for `gateway-verified-target.json` but no discard operation. `ClawbarPanel.qml:246-297` exposes candidate verification only while candidates are already in the current setup state; there is no reset or fallback-management action.
- **Severity:** `medium`. The product remains usable with the stored Gateway, but changing a stale or wrong selection requires undocumented filesystem intervention.
- **Decision needed:** `product call`. Add a private-safe “Forget verified fallback” action, or explicitly declare fallback management out of scope and document the supported reset procedure.
- **Raised by:** [Fallback Gateway setup](gateway/fallback-setup.md#open-questions-and-verification), [Plugin lifecycle](cross-cutting/plugin-lifecycle.md#interactions-with-other-systems).

### B-04: Removing or disabling a failing target silently ends Incident monitoring

- **Where the user meets it:** An enabled Automation is failing and has notified, then is disabled or removed; similarly, an active Gateway Incident transitions to Gateway Setup Required.
- **What happens / what was expected:** Clawbar deletes the Incident from per-login monitoring without a recovery or “monitoring ended” notification. Users may interpret silence as an Incident that remains active indefinitely or miss that monitoring stopped.
- **Reproduce:** 1. Start and observe an Automation Failure notification. 2. Disable or remove that Automation. 3. Refresh and inspect notification history. Repeat by moving an Offline/Configuration Error Gateway to Setup Required.
- **Why (from the code):** `scripts/clawbar_incidents.py:64-71` removes the Gateway incident on `setup_required` without calling `recover`. `scripts/clawbar_incidents.py:93-101` uses `incidents.pop` for disabled or unobserved Automations, also without adding a recovery or distinct unmonitored change.
- **Severity:** `medium`. Operational state is correct in the panel, but the notification lifecycle becomes ambiguous in an uncommon transition.
- **Decision needed:** `product call`. Keep silent unmonitoring, send a recovery, or introduce explicit “monitoring ended” wording that does not claim the underlying condition recovered.
- **Raised by:** [Incidents and notifications](cross-cutting/incidents-and-notifications.md#open-questions-and-verification), [Automation schedules and results](automations/schedules-and-results.md#open-questions-and-verification).

### B-05: Failed notification delivery permanently consumes the transition

- **Where the user meets it:** A new Incident starts or recovers while `notify-send` is unavailable, times out, or returns an error.
- **What happens / what was expected:** No notification reaches the user, yet the transition is persisted first. Later collections see the Incident as already known and never retry the missed notification. A transient notification failure should not silently consume the only delivery attempt.
- **Reproduce:** 1. Clear per-login Incident state. 2. Make `notify-send` unavailable or slower than 0.25 seconds. 3. Start an Incident. 4. Restore notifications. 5. Refresh the unchanged Incident.
- **Why (from the code):** `scripts/clawbar_incidents.py:125-137` suppresses launch errors/timeouts and does not inspect a nonzero return code. `scripts/clawbar_incidents.py:145-153` atomically writes the reconciled state before dispatching starts and recoveries, so the next collection deduplicates a notification that was never delivered.
- **Severity:** `medium`. The panel remains accurate, but users relying on notifications can miss an Incident or recovery permanently for that continuous period.
- **Decision needed:** `fix`. Persist delivery state separately, retry boundedly after failed dispatch, or only mark the transition delivered after confirmed command success.
- **Raised by:** [Incidents and notifications](cross-cutting/incidents-and-notifications.md#open-questions-and-verification).

### B-06: Plugin removal has no cleanup path for persisted Clawbar state

- **Where the user meets it:** The user removes Clawbar after it has collected a Snapshot or verified a Tailscale fallback.
- **What happens / what was expected:** The widget and service unload, but the implementation has no removal hook to delete the Snapshot, candidate endpoint mapping, verified fallback endpoint, or a state-backed key secret. Users may reasonably expect removal either to erase plugin-owned state or to state clearly what is retained.
- **Reproduce:** 1. Populate `snapshot.json`, `gateway-candidates.json`, and `gateway-verified-target.json` through normal use. 2. Remove the plugin with the documented command. 3. Inspect the XDG state directory.
- **Why (from the code):** `manifest.json:9-20` declares only bar-widget and service entry points, with no removal/cleanup hook. Persistent paths are created by `scripts/clawbar_gateway.py:134-135,261-288`, `scripts/clawbar_target_state.py:20-44`, and the state fallback in `scripts/clawbar_metadata.py:21-45`; no corresponding lifecycle cleanup exists. The user documentation at `README.md:106-117` promises process cleanup but does not describe data retention.
- **Severity:** `medium`. The retained files are private and bounded, but include a verified private endpoint and survive the user's explicit removal action.
- **Decision needed:** `product call`. Delete plugin-owned persistent state on remove, preserve it intentionally for reinstall, or add explicit removal/reset documentation and a supported cleanup command.
- **Raised by:** [Plugin lifecycle](cross-cutting/plugin-lifecycle.md#open-questions-and-verification), [Privacy boundary](cross-cutting/privacy-boundary.md#open-questions-and-verification).

## Low

No low-severity code-supported defects were retained after deduplication. Visual and copy questions remain verification items until observed.
