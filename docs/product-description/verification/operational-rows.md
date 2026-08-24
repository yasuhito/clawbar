# Verification: operational rows

Use sanitized Snapshots and fixtures. Never put Private Content into a real notification or screenshot. “Filesystem” checks the reduced Snapshot; “screen reader” checks the real Qt accessibility tree.

## foundations/operational-model.md

| ID | P | Device | Claim | Setup | Steps | Expected | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MODEL-01 | P1 | demo | Panel order is Fleet, independent Agents, then independent Automations ([The model](../foundations/operational-model.md#the-model)). | Populated all-sections demo. | 1. Open panel.<br>2. Inspect headings and rows. | Agents and Automations are not nested under Nodes; sections follow documented order. | — |
| MODEL-02 | P1 | demo | Agent Activity and previous Task Result remain independent ([Agents and Tasks](../foundations/operational-model.md#agents-and-tasks)). | Working Agent with prior Failed result. | 1. Open panel.<br>2. Select Agent. | Row says Working while detail/result says Task Failed; no Gateway Incident roll-up. | — |
| MODEL-03 | P1 | demo | Disabled, skipped, completed, waiting, healthy, and failed Automation meanings remain distinct ([Automations](../foundations/operational-model.md#automations)). | Fixture containing every accepted state. | 1. Inspect every row/detail. | Each uses its documented label; only enabled error is Automation Failure. | — |
| MODEL-04 | P1 | filesystem | Bound or unsafe reduction failure makes the whole section unavailable instead of partial ([Data boundaries and limits](../foundations/operational-model.md#data-boundaries-and-limits)). | Over-bound Automations and invalid Node key cases. | 1. Collect.<br>2. Inspect Snapshot and panel. | Section `available` false, no partial rows, Gateway Degraded. | — |
| MODEL-05 | P1 | demo | Offline Nodes do not affect Gateway health, Attention count, Incident state, or notification ([Fleet and Nodes](../foundations/operational-model.md#fleet-and-nodes)). | Healthy Gateway with only Offline Nodes. | 1. Open panel.<br>2. Inspect bar and notifications. | Node rows muted; Gateway remains healthy and count unchanged. | — |
| MODEL-06 | P1 | screen reader | Visually quiet healthy rows and the Idle Agent ring retain accessible meaning ([Interactions with other systems](../foundations/operational-model.md#interactions-with-other-systems)). | Healthy Node/Automation and Idle Agent. | 1. Traverse rows with accessibility tool.<br>2. Select the Idle Agent. | Names and state meanings are exposed; Idle uses a muted outline ring, omits repeated row text, and remains explicit in accessibility and detail. | — |

Not checkable by hand: private identity derivation is verified from reduced output and tests, not accessibility or layout observation.

## fleet/nodes.md

| ID | P | Device | Claim | Setup | Steps | Expected | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NODE-01 | P1 | demo | Same-named registrations collapse to the freshest connected Node ([Settled](../fleet/nodes.md#settled)). | Fixtures with connected/disconnected duplicate registrations. | 1. Collect.<br>2. Open Fleet. | One row per display name; freshest connected metadata shown. | — |
| NODE-02 | P1 | demo | Node selection survives reordered and replacement registration through stable UI key ([While waiting](../fleet/nodes.md#while-waiting)). | Select duplicate-name Node then reorder/replace fixture. | 1. Select row.<br>2. Refresh fixtures. | Visible Node remains selected and detail updates to replacement metadata. | — |
| NODE-03 | P1 | demo | Offline Node is muted, explicit, and non-Incident ([The simple case](../fleet/nodes.md#the-simple-case)). | Healthy Gateway with offline Node. | 1. Open panel and tooltip.<br>2. Check notifications. | Muted Offline row; no Attention count or notification. | — |
| NODE-04 | P2 | mouse | Selected Node expands platform, model, version, and observation detail without control action ([Invoked](../fleet/nodes.md#invoked)). | Node with all fields. | 1. Click row.<br>2. Inspect OpenClaw state. | Bounded detail appears; no Node operation occurs. | — |
| NODE-05 | P1 | filesystem | Missing safe Node identity makes Fleet unavailable rather than using private/positional identity ([Edge cases](../fleet/nodes.md#edge-cases)). | Node without private identity or invalid local secret. | 1. Collect.<br>2. Inspect Snapshot/panel. | No private ID; Fleet unavailable and Gateway Degraded. | — |
| NODE-06 | P1 | screen reader | Node name and current/historical state are exposed accessibly ([Open questions and verification](../fleet/nodes.md#open-questions-and-verification)). | Healthy, offline, historical Nodes. | 1. Traverse each row. | Accessible name is display name; description distinguishes state/Last known. | — |

Not checkable by hand: whether display-name-based identity is the right product identity when two physical Nodes intentionally share a name.

## agents/activity-and-task-results.md

| ID | P | Device | Claim | Setup | Steps | Expected | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AGENT-01 | P1 | demo | Working, Waiting, and Idle current activities remain independent from Succeeded, Failed, and None Task Results ([Settled](../agents/activity-and-task-results.md#settled)). | Matrix fixture of activities/results. | 1. Open panel.<br>2. Select every Agent. | Row activity and previous Task Result each match fixture without roll-up. | — |
| AGENT-02 | P1 | demo | Failed Task Result does not create an Attention Item, Incident, or notification ([Interactions with other systems](../agents/activity-and-task-results.md#interactions-with-other-systems)). | Healthy Gateway; one Agent prior failure; no Automation failure. | 1. Refresh.<br>2. Inspect bar and notification history. | Failed result visible only on Agent; Gateway remains healthy and quiet. | — |
| AGENT-03 | P2 | demo | Empty Agent list omits the entire section ([The simple case](../agents/activity-and-task-results.md#the-simple-case)). | Available empty Agents with nonempty other sections. | 1. Open panel. | No `AGENTS` heading or empty message; other sections remain. | — |
| AGENT-04 | P2 | keyboard | Selection follows Agent key across Gateway-order changes ([While waiting](../agents/activity-and-task-results.md#while-waiting)). | Select Agent then publish reordered list. | 1. Select Agent.<br>2. Refresh reorder. | Same Agent stays selected at new position. | — |
| AGENT-05 | P2 | demo | Historical Agent row says Last known and retains bounded previous Task context ([Settled](../agents/activity-and-task-results.md#settled)). | Current then unstable/stale state. | 1. Select Agent.<br>2. Transition historical. | Reduced emphasis and Last known; current activity no longer claimed live. | — |
| AGENT-06 | P1 | screen reader | Agent name, Activity, and failed Task Result are discoverable accessibly ([Open questions and verification](../agents/activity-and-task-results.md#open-questions-and-verification)). | Working/Failed and Idle/None Agents. | 1. Traverse rows and detail.<br>2. Compare the Idle row with its selected detail. | Screen reader exposes current activity and separate previous result; Idle remains named despite its visually omitted row label. | — |

Not checkable by hand: whether omitting `No Agents` is preferable to matching Fleet/Automation empty messages.

## automations/schedules-and-results.md

| ID | P | Device | Claim | Setup | Steps | Expected | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AUTO-01 | P1 | demo | Each enabled current Automation Failure contributes exactly one Attention Item regardless of consecutive count ([Interactions with other systems](../automations/schedules-and-results.md#interactions-with-other-systems)). | One failure with count 1, then count 78. | 1. Refresh each.<br>2. Inspect bar/detail. | Bar count remains one; detail changes consecutive-failure text. | — |
| AUTO-02 | P1 | demo | Disabled Automation with retained error is Disabled, not an Automation Failure ([Edge cases](../automations/schedules-and-results.md#edge-cases)). | Disabled item with lastResult error. | 1. Open panel.<br>2. Inspect bar/notification. | Dotted Disabled row; no Attention count or Incident. | — |
| AUTO-03 | P2 | demo | Schedule kinds and timing labels distinguish scheduled, repeating, one-time, and event-driven items ([Settled](../automations/schedules-and-results.md#settled)). | Fixture with every kind. | 1. Select each row. | Detail shows correct kind and next/last local times or appropriate absence. | — |
| AUTO-04 | P2 | keyboard | Enter and selection never run, retry, cancel, edit, enable, disable, or delete an Automation ([Invoked](../automations/schedules-and-results.md#invoked)). | Select each state. | 1. Press Enter.<br>2. Compare Gateway Automation state. | Detail only; no OpenClaw mutation. | — |
| AUTO-05 | P2 | demo | Healthy routine status may be visually omitted while exceptional/historical states remain explicit ([Theme and accessibility](../automations/schedules-and-results.md#interactions-with-other-systems)). | Healthy, failed, disabled, historical rows. | 1. Compare summaries. | Healthy saves space; Failed/Disabled/Last known labels remain visible. | — |
| AUTO-06 | P1 | screen reader | Visually omitted healthy Automation still exposes accessible state description ([Open questions and verification](../automations/schedules-and-results.md#open-questions-and-verification)). | Healthy scheduled Automation. | 1. Traverse row with accessibility inspector. | Accessible name and `Healthy` description are present. | — |
| AUTO-07 | P1 | notification | Removing or disabling a failing Automation ends monitoring without recovery (product concern) ([Edge cases](../automations/schedules-and-results.md#edge-cases)). | Start current Automation Incident and clear notification. | 1. Remove/disable item.<br>2. Refresh.<br>3. Inspect notifications. | Record what happens; current code is expected to send no recovery. | — |
| AUTO-08 | P3 | themes | Long names and large failure counts elide without obscuring selected detail ([Open questions and verification](../automations/schedules-and-results.md#open-questions-and-verification)). | Narrow panel; long sanitized names and count. | 1. Open rows.<br>2. Select each. | Summary elides cleanly; detail remains readable and bounded. | — |

Not checkable by hand: whether silent unmonitoring should be called recovery is a product decision after AUTO-07.
