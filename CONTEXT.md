# Clawbar

Clawbar gives an Omarchy user a read-only operational view of the OpenClaw Nodes managed by the configured Gateway.

## Language

**Gateway**:
The single OpenClaw Gateway Clawbar connects to through the local OpenClaw configuration. It may run on the current device or at the configured remote URL, and is the source of the Fleet, Agent, Task, and Automation metadata shown by Clawbar.
_Avoid_: Node, Fleet, server

**Gateway Target**:
The endpoint Clawbar connects to. OpenClaw configuration or node-host state resolves it automatically when available. If neither identifies a Gateway, the user may choose one Tailscale device as a fallback candidate; Clawbar must verify that the candidate runs the supported Gateway before using it.
_Avoid_: Node, Gateway

**Gateway Setup Required**:
No local Gateway is running and neither OpenClaw configuration nor node-host state identifies a remote Gateway. It requires the user to choose and verify a fallback device, uses the yellow state, and is not an Incident.
_Avoid_: Empty Fleet, Offline Gateway, Configuration Error

**Unstable Gateway**:
The latest attempt to collect from a previously reachable Gateway failed, without yet reaching two consecutive failures.
_Avoid_: Offline Gateway, Offline Node

**Degraded Gateway**:
A reachable Gateway whose core status is current but whose Task or Automation metadata could not be collected. Unavailable sections show no carried-forward values.
_Avoid_: Offline Gateway, Stale Snapshot

**Offline Gateway**:
The configured Gateway whose two most recent collection attempts both failed.
_Avoid_: Unstable Gateway, Offline Node, stale

**Configuration Error**:
A Gateway Target that is reachable but lacks the supported OpenClaw command surface. It is immediately actionable and distinct from an Offline Gateway.
_Avoid_: Offline Gateway, unsupported Node

**Node**:
An operational unit managed and reported by the configured Gateway. Clawbar does not connect to Nodes directly.
_Avoid_: Gateway, Gateway Target, host, machine

**Node UI Key**:
A local opaque identifier derived from a private Node identifier with Clawbar's local secret. It preserves selection and expansion across Fleet snapshots; neither the private identifier nor the secret enters the snapshot. If Clawbar cannot derive every Node UI Key, Fleet metadata is unavailable.
_Avoid_: Node ID, instance ID, positional index

**Fleet**:
The set of Nodes reported by the configured Gateway.
_Avoid_: Gateways, cluster

**Offline Node**:
A Node whose unavailable state is reported by the configured Gateway. Clawbar does not infer this state from a direct Node probe.
_Avoid_: Offline Gateway, Unstable Gateway

**Degraded Node**:
A Node whose core state is current but whose Task or Automation metadata is unavailable. The unavailable child state rolls up to the parent Node as yellow, and failed-section values are not carried forward.
_Avoid_: Degraded Gateway, Offline Node

**Automation Failure**:
An unsuccessful result reported by the Gateway for an Automation run. Unlike a collection failure, it is immediately actionable.
_Avoid_: Gateway failure, Node failure

**Disabled Automation**:
An Automation that remains configured but is not scheduled to run. It remains visible by name and last-run time as muted Operational Metadata but never creates an Attention Item or Incident.
_Avoid_: Automation Failure, unavailable Automation

**Stale Snapshot**:
A Fleet snapshot whose age exceeds three configured refresh intervals. It no longer establishes current Gateway or Node health.
_Avoid_: Offline Gateway, Offline Fleet, cached failure

**Incident**:
A continuous period in which the Gateway is Offline, a Node is reported Offline, a Gateway Target has a Configuration Error, or an Automation has a current failure. It produces at most one failure notification and one recovery notification per desktop login.
_Avoid_: Alert, event, Gateway Setup Required

**Operational Metadata**:
The bounded, non-content fields Clawbar may persist and display, such as Gateway and Node state, model/runtime, Automation name, result, and timestamps.
_Avoid_: Task data, message data

**Private Content**:
Task instructions, message bodies, destinations, account identifiers, and raw errors. Clawbar never persists or displays them.
_Avoid_: Details, metadata

**Agent Activity**:
An Agent's present work state: Working, Waiting, or Idle. Waiting and Idle are not Incidents and remain independent of earlier Task Results.
_Avoid_: Agent status

**Task Result**:
The outcome and completion time of an Agent's most recently completed Task: Succeeded, Failed, or None. A Failed Task Result neither changes Agent Activity nor rolls up to Node or Gateway health.
_Avoid_: Agent failure, Agent Activity

**Attention Item**:
An Offline or Unstable Gateway, a Degraded Gateway, an Offline or Degraded Node reported by the Gateway, a Configuration Error, an Automation Failure, or a Stale Snapshot. Gateway-level items may appear before the Fleet tree. Node and Automation items stay in the tree and roll up to their parent Node instead of being duplicated in a separate summary. Gateway Setup Required is handled by the setup form.
_Avoid_: Task failure, notification, setup state

**Empty Fleet**:
A connected Gateway that currently reports no Nodes. It is distinct from Gateway Setup Required and is not an Incident.
_Avoid_: Offline Fleet, Gateway Setup Required

**Last Known Metadata**:
Operational Metadata retained from the last successful Gateway collection. It preserves the last observed state while freshness is expressed separately; it never establishes a current Incident and is excluded from current Fleet counts.
_Avoid_: Current state, Stale Snapshot
