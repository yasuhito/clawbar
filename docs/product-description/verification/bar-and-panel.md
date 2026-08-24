# Verification: bar and panel

Run with default placement and interval. Use `healthy`, `automation-failure`, `stale-snapshot`, and `empty-fleet` developer scenarios as named. “Mouse” and “keyboard” mean real input to the Omarchy panel; “demo” means the script establishes state but the UI is still observed by hand.

## foundations/surface-and-actions.md

| ID | P | Device | Claim | Setup | Steps | Expected | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SURF-01 | P1 | mouse | Normal press opens the one anchored panel; middle-click requests refresh without toggling it ([Invoked](../foundations/surface-and-actions.md#invoked)). | Healthy demo, panel closed. | 1. Normal-click the claw.<br>2. Close it.<br>3. Middle-click the claw. | Normal click opens; middle-click leaves the panel closed and requests collection. | — |
| SURF-02 | P1 | keyboard | The focused panel accepts arrows, J/K, Enter for candidates, R for refresh, and Escape for close ([Invoked](../foundations/surface-and-actions.md#invoked)). | Panel open; operational rows, then setup candidates. | 1. Exercise each key on its applicable state.<br>2. Record the visible action. | Keys map to the documented Actions; Enter does not activate operational rows. | — |
| SURF-03 | P2 | delayed demo | Closing the panel does not cancel collection or candidate verification ([While waiting](../foundations/surface-and-actions.md#while-waiting)). | Start a delayed request. | 1. Start request.<br>2. Press Escape.<br>3. Reopen after completion. | Panel closes immediately; settled result is visible after reopening. | — |
| SURF-04 | P2 | keyboard | Immediate selection and panel Actions remain responsive while asynchronous work waits ([Waiting begins](../foundations/surface-and-actions.md#waiting-begins)). | Delayed collection, panel open. | 1. Start refresh.<br>2. Move selection repeatedly.<br>3. Toggle panel. | Selection and panel response do not wait for the Gateway. | — |
| SURF-05 | P2 | demo | Candidate verification alone shows `Verifying…`; ordinary refresh has no global busy state ([While waiting](../foundations/surface-and-actions.md#while-waiting)). | Existing healthy snapshot, then delayed setup verification. | 1. Refresh healthy state.<br>2. Verify candidate. | Refresh retains existing presentation; selected candidate explicitly shows `Verifying…`. | — |

Not checkable by hand: whether all compositor pointer button codes map identically outside the supported Omarchy environment.

## foundations/selection-model.md

| ID | P | Device | Claim | Setup | Steps | Expected | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SEL-01 | P1 | keyboard | Selection order is candidates or Nodes, then Agents, then Automations ([Ordered rows](../foundations/selection-model.md#ordered-rows)). | Demo with all operational sections; setup demo separately. | 1. Open panel.<br>2. Press Down through every row. | Selection follows the documented single order across section boundaries. | — |
| SEL-02 | P1 | keyboard | Forward and backward movement wraps at both ends ([Movement and wrapping](../foundations/selection-model.md#movement-and-wrapping)). | At least three rows. | 1. Select last row.<br>2. Press Down.<br>3. Press Up. | Moves to first, then back to last. | — |
| SEL-03 | P1 | demo | Snapshot reorder retains the same stable selected object ([Snapshot reconciliation](../foundations/selection-model.md#snapshot-reconciliation)). | Select a Node/Automation; prepare reordered Snapshot with same key. | 1. Select object.<br>2. Publish reordered Snapshot. | Same object remains selected even at a new index. | — |
| SEL-04 | P2 | demo | Removing the selected row chooses a surviving row near the previous index ([Snapshot reconciliation](../foundations/selection-model.md#snapshot-reconciliation)). | Select middle then last row in controlled Snapshots. | 1. Remove selected row.<br>2. Repeat for last row. | Replacement uses old index when possible; otherwise new last row. | — |
| SEL-05 | P2 | keyboard | Moving selection scrolls only enough to reveal the selected row ([Movement and wrapping](../foundations/selection-model.md#movement-and-wrapping)). | Narrow panel with enough rows to scroll. | 1. Move below viewport.<br>2. Move above viewport. | Selected bottom/top edge becomes visible without unrelated jump. | — |
| SEL-06 | P2 | mouse | Operational click selects only; candidate click selects and activates ([Pointer selection and activation](../foundations/selection-model.md#pointer-selection-and-activation)). | Operational then setup state. | 1. Click operational row.<br>2. Click candidate. | Operational detail opens without external work; candidate verification starts. | — |

Not checkable by hand: private stable-key derivation itself; inspect tests and safe Snapshot output instead.

## bar/manual-refresh.md

| ID | P | Device | Claim | Setup | Steps | Expected | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REF-01 | P1 | keyboard | `r` and `R` request non-blocking refresh while the panel remains interactive ([Invoked](../bar/manual-refresh.md#invoked)). | Healthy panel and delayed Gateway. | 1. Press `r`.<br>2. Move selection during delay.<br>3. Repeat with `R`. | Both request refresh; navigation remains immediate. | — |
| REF-02 | P1 | mouse | Middle-click refresh works with panel open or closed and does not toggle it ([Ready](../bar/manual-refresh.md#ready)). | Healthy demo. | 1. Middle-click closed panel.<br>2. Open panel and middle-click. | Refresh requested in both cases; visibility does not toggle. | — |
| REF-03 | P1 | delayed demo | Repeated refreshes coalesce into at most one follow-up collection ([While waiting](../bar/manual-refresh.md#while-waiting)). | Collector call log and delayed first collection. | 1. Start refresh.<br>2. Press `r` ten times.<br>3. Wait for idle. | Exactly current collection plus at most one follow-up; no overlap. | — |
| REF-04 | P1 | delayed demo | Existing Snapshot has no visible refresh-in-progress indication (suspected bug) ([Waiting begins](../bar/manual-refresh.md#waiting-begins)). | Existing healthy Snapshot; 8-second collection. | 1. Press `r`.<br>2. Observe bar and panel until completion. | Record what happens; current code is expected to show no busy marker. | — |
| REF-05 | P1 | demo | Missing collector service with an old Snapshot gives no panel error (suspected bug) ([Invoked](../bar/manual-refresh.md#invoked)). | Old Snapshot loaded; run widget without service entry. | 1. Press `r`.<br>2. Inspect panel and shell console. | Record what happens; current code is expected to keep old UI and log only to console. | — |
| REF-06 | P2 | delayed demo | Escape closes only the panel and does not cancel refresh ([Cancel and interrupt](../bar/manual-refresh.md#cancel-and-interrupt)). | Delayed collection. | 1. Press `r`.<br>2. Press Escape.<br>3. Reopen after result. | Result completes and is shown after reopening. | — |
| REF-07 | P3 | demo | First run shows Collecting, while an existing Snapshot remains visible during refresh ([Waiting begins](../bar/manual-refresh.md#waiting-begins)). | Clear Snapshot then repeat with healthy Snapshot. | 1. Request each refresh.<br>2. Observe waiting presentation. | First run says Collecting; existing state remains unchanged until result. | — |

Not checkable by hand: exact internal queue count without collector call logging.

## bar/signal-and-tooltip.md

| ID | P | Device | Claim | Setup | Steps | Expected | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SIG-01 | P1 | demo | Bar severity follows Healthy, warning, and critical state while tooltip names the condition ([Settled](../bar/signal-and-tooltip.md#settled)). | Healthy, degraded, and offline demos. | 1. Run each scenario.<br>2. Hover claw. | Color changes by severity and tooltip names each state. | — |
| SIG-02 | P1 | demo | Automation Failure makes the bar critical while Gateway reachability stays healthy ([The simple case](../bar/signal-and-tooltip.md#the-simple-case)). | Automation-failure demo. | 1. Observe claw and tooltip.<br>2. Open panel header. | Critical signal and Attention count coexist with healthy Gateway metadata. | — |
| SIG-03 | P1 | demo | Multiple Incidents have no visible numeric badge (product concern) ([Summary](../bar/signal-and-tooltip.md#summary)). | Grouped-incidents demo. | 1. Observe closed bar.<br>2. Hover tooltip. | Record clarity; no badge is drawn, but tooltip contains plural count. | — |
| SIG-04 | P2 | demo | Developer demonstration prefixes tooltip without replacing normal summary ([Settled](../bar/signal-and-tooltip.md#settled)). | Any demo scenario. | 1. Hover claw. | Tooltip begins `Developer demo ·` followed by normal state summary. | — |
| SIG-05 | P2 | shell | The two-path claw shown beside elapsed time in OpenClaw chat gives restrained activity feedback without adding a status glyph ([Invoked](../bar/signal-and-tooltip.md#invoked)). | Healthy Snapshot; collection idle, then running. | 1. Observe idle claw.<br>2. Hover it.<br>3. Start collection and move pointer away.<br>4. Wait for collection to finish. | Resting pose is stable; hover and collection reproduce OpenClaw's body flex and upper-jaw snip; the joint remains closed and the mark returns to rest afterward. | — |
| SIG-06 | P3 | themes | Healthy uses theme green, warning theme yellow, critical shell urgent color with fallback behavior ([Theme and accessibility](../bar/signal-and-tooltip.md#interactions-with-other-systems)). | Four release themes. | 1. Exercise three severities in each theme.<br>2. Measure/inspect contrast. | Signals remain distinguishable and tooltip text is readable. | — |

Not checkable by hand: whether the visual no-badge choice is intentional; that requires a product decision.

## panel/opening-and-closing.md

| ID | P | Device | Claim | Setup | Steps | Expected | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OPEN-01 | P1 | mouse | Normal widget presses toggle one anchored panel ([Invoked](../panel/opening-and-closing.md#invoked)). | Panel closed. | 1. Click claw.<br>2. Click again. | One panel opens, then closes; no duplicate surface appears. | — |
| OPEN-02 | P1 | keyboard | Escape closes the focused panel without stopping collection ([Cancel and interrupt](../panel/opening-and-closing.md#cancel-and-interrupt)). | Open panel during delayed refresh. | 1. Press Escape.<br>2. Reopen after completion. | Panel closes and later result is present. | — |
| OPEN-03 | P2 | mouse | Outside-click dismissal and focus return behave like the supported shell panel ([Open questions and verification](../panel/opening-and-closing.md#open-questions-and-verification)). | Panel open. | 1. Click outside.<br>2. Reopen with keyboard/pointer. | Record dismissal and focus return; no stuck focus remains. | — |
| OPEN-04 | P2 | demo | Snapshot changes update open content but do not force a closed panel open ([Cancel and interrupt](../panel/opening-and-closing.md#cancel-and-interrupt)). | Observe open then closed panel while changing demo. | 1. Change scenario open.<br>2. Close and change again. | Open panel updates; closed panel remains hidden. | — |
| OPEN-05 | P3 | themes | Placement and inherited motion work on each bar edge and honor reduced motion if supported ([Open questions and verification](../panel/opening-and-closing.md#open-questions-and-verification)). | Move bar through supported edges; toggle reduced motion. | 1. Open/close on each edge.<br>2. Repeat reduced motion. | Panel remains anchored and on-screen; record motion behavior. | — |

Not checkable by hand: no source contract promises persistence of selection across complete shell recreation.

## panel/navigation-and-details.md

| ID | P | Device | Claim | Setup | Steps | Expected | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NAV-01 | P1 | keyboard | Arrow and J/K keys move one shared Selection and wrap across sections ([Invoked](../panel/navigation-and-details.md#invoked)). | All-sections demo. | 1. Exercise Up/Down/Left/Right and J/K.<br>2. Cross section boundaries. | Each direction maps as documented; one selected row remains. | — |
| NAV-02 | P1 | keyboard | Enter on operational rows does nothing (accessibility concern) ([Edge cases](../panel/navigation-and-details.md#edge-cases)). | Select Node, Agent, Automation in turn. | 1. Press Enter on each.<br>2. Observe detail and external state. | Record what happens; no activation, command, or feedback occurs. | — |
| NAV-03 | P2 | mouse | Selecting a row expands bounded detail directly beneath it and moves the single detail ([Settled](../panel/navigation-and-details.md#settled)). | Operational rows. | 1. Click Node.<br>2. Click Agent.<br>3. Click Automation. | Only selected row shows its detail; old detail collapses. | — |
| NAV-04 | P2 | demo | Refresh reorder retains stable Selection and scrolls it into view ([While waiting](../panel/navigation-and-details.md#while-waiting)). | Select object then publish reordered Snapshot outside viewport. | 1. Refresh reorder.<br>2. Observe selection and scroll. | Same object selected and visible. | — |
| NAV-05 | P1 | screen reader | Row names, state descriptions, and dynamic detail are announced ([Theme and accessibility](../panel/navigation-and-details.md#interactions-with-other-systems)). | Screen reader; all row kinds. | 1. Traverse each row.<br>2. Change Selection. | Name and current/historical state are announced; detail change is discoverable. | — |

Not checkable by hand: none; unresolved accessibility behavior is intentionally observable here.

## panel/empty-and-unavailable-states.md

| ID | P | Device | Claim | Setup | Steps | Expected | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EMPTY-01 | P1 | demo | Healthy Empty Fleet shows `FLEET` and `Empty Fleet`, not setup or failure ([The simple case](../panel/empty-and-unavailable-states.md#the-simple-case)). | Empty-fleet demo. | 1. Open panel. | Healthy header plus explicit Empty Fleet; no Incident. | — |
| EMPTY-02 | P2 | demo | Empty Agents omits the section while empty Automations says `No Automations` ([Summary](../panel/empty-and-unavailable-states.md#summary)). | Snapshot with all three available and empty. | 1. Open panel.<br>2. Compare sections. | Fleet and Automations show empty text; Agents heading is absent. | — |
| EMPTY-03 | P1 | demo | Degraded metadata sections say unavailable and do not carry old values forward ([Settled](../panel/empty-and-unavailable-states.md#settled)). | Prior populated Snapshot then degraded demo. | 1. Open populated state.<br>2. Publish degraded state. | Failed section is unavailable/empty; no stale values shown as current. | — |
| EMPTY-04 | P1 | demo | More than 500 Automations shows explicit section unavailability rather than a truncated healthy list ([Edge cases](../panel/empty-and-unavailable-states.md#edge-cases)). | Controlled Snapshot with reason `more_than_500`. | 1. Open panel. | Text says `Unavailable — more than 500 Automations`; no partial rows. | — |
| EMPTY-05 | P2 | demo | First-run Collecting, No data, Setup Required, Configuration Error, and Stale remain visually distinct ([Action, event by event](../panel/empty-and-unavailable-states.md#the-action-event-by-event)). | Run matching demos/controlled first failure. | 1. Observe each state at narrow width. | Each has distinct summary/guidance; content does not overlap or clip. | — |
| EMPTY-06 | P1 | screen reader | Populated-to-unavailable transition and resulting Selection change are announced ([Open questions and verification](../panel/empty-and-unavailable-states.md#open-questions-and-verification)). | Screen reader and selected row in section that becomes unavailable. | 1. Publish unavailable state.<br>2. Inspect announcement/focus. | Record what happens; user is not left on an undiscoverable removed row. | — |

Not checkable by hand: whether the three different empty-section conventions are a deliberate product choice.
