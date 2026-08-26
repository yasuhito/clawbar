# Glossary

The vocabulary used across these documents. When a document uses one of these terms, it means exactly this.

## The surface

**Clawbar.** The read-only OpenClaw Fleet signal board installed as an Omarchy bar widget with one popup panel and one collection service. Clawbar observes one Gateway; it does not control OpenClaw work.

**Bar widget.** The compact Clawbar control in the Omarchy bar. Its claw mark changes color with current severity. Pressing it toggles the panel; middle-clicking it requests a refresh.

**Panel.** The popup surface anchored to the bar widget. It shows the Gateway summary followed, when available, by Gateway candidates, Fleet Nodes, Agents, and Automations. It holds one selection across all actionable rows.

**Developer demonstration.** A development-only mode that writes fictional sanitized snapshots through Clawbar's normal snapshot boundary. The panel prefixes its summary with `Developer demo` so that those states cannot be mistaken for current Gateway data.

## Gateway and setup

**Gateway.** The single OpenClaw Gateway Clawbar connects to through local OpenClaw configuration or a verified fallback. It supplies all Fleet, Agent, Task, and Automation metadata shown by Clawbar. Clawbar does not connect to Nodes directly.

**Gateway Target.** The endpoint Clawbar connects to. OpenClaw normally resolves it from local, configured remote, or Node-host state. If none is available, Clawbar may reuse one previously verified Tailscale fallback.

**Gateway candidate.** An online Tailscale device offered when OpenClaw cannot resolve a Gateway. A candidate is not a Gateway Target until Clawbar verifies that the supported read-only Gateway JSON surface responds.

**Gateway Candidate Key.** A per-login opaque key derived from a private Tailscale device identifier and Clawbar's local secret. It keeps selection attached to the same candidate across reordering without placing the private identifier in the snapshot.

**Gateway Setup Required.** The non-Incident state in which OpenClaw has not resolved a Gateway and Clawbar needs the user to verify a fallback candidate. It is shown in yellow and contributes no Attention Item.

**Configuration Error.** A reachable Gateway Target that does not provide the supported OpenClaw command surface. It is red, actionable, and distinct from an Offline Gateway.

## Operational objects

**Fleet.** The flat set of Nodes reported by the Gateway. The order comes from Gateway metadata; Clawbar does not present a topology or parent-child relationship.

**Node.** An operational unit reported by the Gateway. A Node has a display name and may have bounded platform, model, version, state, and observation time metadata. Clawbar does not probe Nodes directly.

**Node UI Key.** A stable opaque key derived from a Node identity and Clawbar's local secret. It preserves selection across refreshed and reordered snapshots without exposing the private Node identifier.

**Agent.** A named OpenClaw agent reported by the Gateway. Clawbar shows it independently of Nodes because the supported metadata does not establish Node ownership.

**Registered Agent.** An Agent entry reported by the configured Gateway. Its green dot confirms only registration, not health, online presence, or current activity.

**Task Result.** The outcome and completion time of a Registered Agent's most recently completed Task: Succeeded, Failed, or None. A Failed Task Result does not establish Agent health or current activity and is not an Incident.

**Automation.** A scheduled operation managed by the Gateway and shown in the independent Automations section. Clawbar can observe it but cannot create, edit, retry, cancel, enable, disable, or delete it.

**Automation ID.** The opaque Gateway-provided identifier retained only to preserve Automation selection across refreshed snapshots. It is not shown to the user.

**Automation Failure.** An error result for an enabled Automation. It creates one current Attention Item and an Incident, but it does not change Gateway or Node state.

**Disabled Automation.** An Automation that remains configured but is not scheduled to run. It remains visible as muted Operational Metadata and does not create an Attention Item or Incident.

## Health and freshness

**Operational Metadata.** Bounded non-content fields that Clawbar may persist and display, including generalized states, display names, model and runtime labels, Automation schedule metadata, timestamps, and opaque UI keys.

**Private Content.** Task instructions, message bodies, destinations, account identifiers, credentials, private host or network identifiers, and raw errors. Clawbar neither persists nor displays Private Content.

**Snapshot.** The atomically replaced, versioned file from which the bar widget and panel read all operational state. The default location is `$XDG_STATE_HOME/clawbar/snapshot.json`, or `~/.local/state/clawbar/snapshot.json` when `XDG_STATE_HOME` is unset.

**Current metadata.** Operational Metadata from a successful collection that has not crossed its stale boundary. It can establish current health, Attention Items, and Incidents.

**Last Known Metadata.** Operational Metadata retained from the latest successful collection after current collection can no longer establish live health. It is shown with reduced emphasis, a `Last known` label, and an observation time. It never establishes a current Incident or contributes its old item count.

**Healthy Gateway.** A Gateway whose core status and requested metadata are current and available. A healthy Gateway may still coexist with Automation Failures, so the panel header and bar can show critical Incident severity while Gateway reachability remains healthy.

**Degraded Gateway.** A reachable Gateway whose core status is current but whose Fleet, Agent/Task, or Automation metadata could not all be collected — including when collection output was discarded for exceeding the bounded-size limit. Unavailable sections show no carried-forward values.

**Unstable Gateway.** A previously reachable Gateway after one consecutive failed collection. Last Known Metadata remains visible, but the previous snapshot no longer establishes current health.

**Offline Gateway.** A configured Gateway after two consecutive failed collections. It is a current Incident and is distinct from an Offline Node.

**Offline Node.** A Node that the Gateway reports as unavailable. It is muted Operational Metadata and never creates an Attention Item or Incident.

**Stale Snapshot.** A snapshot older than three accepted refresh intervals. It is a yellow current state; retained rows become Last Known Metadata even when the snapshot previously described a red Incident.

**Empty Fleet.** A current, reachable Gateway that reports no Nodes. It is neither Gateway Setup Required nor an Incident.

## Attention and notifications

**Attention Item.** One current condition counted by the bar: an Unstable or Offline Gateway, a Degraded Gateway, a Configuration Error, an Automation Failure, or a Stale Snapshot. Offline Nodes and Gateway Setup Required do not count.

**Incident.** A continuous period in which the Gateway is Offline, a Gateway Target has a Configuration Error, or at least one Automation has a current failure. One continuous period produces at most one grouped failure notification and one grouped recovery notification per desktop login.

**Severity.** The compact presentation level used by the bar and header: healthy, warning, or critical. Severity controls color and summary text but is not itself a Gateway state.

## Actions and input

**Action.** One user interaction with Clawbar, such as toggling the panel, moving selection, requesting a refresh, or verifying a Gateway candidate. An Action may settle immediately or wait for an external process.

**Ready.** The phase before an Action begins, when Clawbar can accept input and the document's starting conditions are true.

**Invoked.** The instant the pointer or keyboard input requests an Action. Clawbar determines the target and either settles immediately or begins waiting.

**Waiting.** The phase after an asynchronous Action has started but before its result is reflected in a consumed snapshot. Selection movement and panel toggling do not enter this phase.

**Settled.** The phase in which the Action's immediate state change or asynchronous result has been consumed. Settled does not always mean successful: a failed collection settles into No data, Unstable, Offline, Configuration Error, or another documented state.

**Selection.** The one current actionable row in the panel. It spans Gateway candidates, Nodes, Agents, and Automations, follows a stable key across reordering, and determines which bounded detail is shown.

**Manual refresh.** A non-blocking collection request made by middle-clicking the bar widget or pressing `r` while the panel has focus. Repeated requests while collection is busy are coalesced into at most one pending refresh.

## Events that cancel or interrupt an action

**Close.** Escape or a panel-close action hides the panel. Closing does not cancel an in-flight collection or candidate verification.

**Competing Action.** Another Clawbar input received while an Action is waiting. Its effect depends on whether the collection service is idle: it may act immediately, replace one pending candidate, or coalesce into one pending refresh.

**Collection completion.** Publication and consumption of a new snapshot after a scheduled refresh, manual refresh, or candidate verification. It can reorder or replace rows and therefore causes selection reconciliation.

**Shell interruption.** Omarchy Shell losing focus, restarting, or exiting. Focus loss and process lifetime have different effects and require hand verification where source tests do not specify them.

**Snapshot transition.** A snapshot being replaced, becoming stale, or failing to parse. The visible result depends on whether Clawbar already has a usable in-memory snapshot.

**Plugin lifecycle change.** Disabling, updating, or removing Clawbar. Disabling or removing unloads scheduling immediately; an already running collector remains bounded by its deadline.

**Input-channel change.** Switching between pointer and keyboard input while the panel is open. Both channels act on the same selection; no separate pointer focus is documented.

**Gateway transition.** Gateway resolution, reachability, or supported-command status changing during collection. The result appears when the next snapshot is consumed rather than mutating the current panel in place.
