# Clawbar product description

A written description of the user experience of Clawbar: what the user sees, what they can do, and exactly what happens when they do it.

## Purpose

Clawbar is, from the user's point of view, a state chart attached to the Omarchy bar. The user moves through it by opening and closing the panel, moving the selection, requesting refreshes, and—when automatic Gateway discovery cannot finish setup—verifying a Tailscale device. Most behavior is defined implicitly across QML components, JavaScript presentation logic, the bounded Python collector, and their tests. There is no single place that says what the user sees after an action, what remains visible while collection is running, and what happens when the Gateway or shell changes state halfway through.

This project is that place. It describes the default Clawbar installation, enabled in the right section of the Omarchy bar, connected to one Gateway chosen by OpenClaw's normal resolution rules or by Clawbar's verified Tailscale fallback. No theme, refresh interval, OpenClaw configuration, or plugin placement is customized unless a document says otherwise.

The documents are for people who need to understand or change Clawbar: designers, engineers, writers, testers, and release reviewers. They are written from the outside in. They describe the experience, not the implementation.

### What this is not

- Not installation or contributor documentation. Those instructions remain in the source repository's `README.md`.
- Not organized by source file. The QML, JavaScript, and Python components are not described separately when they cooperate to produce one visible behavior.
- Not OpenClaw documentation. Gateway, Node, Agent, Task, and Automation behavior is described only where Clawbar observes and presents it.
- Not a technical design document. A technical detail appears only in a `Technical note` block quote when it changes what a user would expect.

## Conventions

- Describe the experience, not the code. “A second refresh request waits for the current collection and then causes one more collection” rather than “`refreshPending` becomes true.”
- Technical detail goes in block quotes prefixed with `Technical note:`. Use it only when the mechanism changes what the user would expect.
- Use sentence case for headings.
- Use the vocabulary in the [glossary](glossary.md), especially Gateway, Gateway Target, Fleet, Node, Registered Agent, Task Result, Automation Failure, Attention Item, Incident, and Last Known Metadata.
- Every document ends with the Clawbar commit it was checked against and a list of open questions.
- State surprising behavior plainly. Do not turn missing evidence into an assumed behavior.

## The work to be done

Each document describes one feature or one set of user-visible rules. Large features, such as Gateway state and fallback setup, and small features, such as manual refresh, use the same questions so that omissions stand out.

### Document template

Every feature document follows the same eight-section skeleton.

1. **Summary.** What the feature is, where the user meets it, and when it is available.
2. **The simple case.** The common path in direct prose.
3. **The action, event by event.** Clawbar's unit of interaction is an action. Its five phases are **ready**, **invoked**, **waiting begins**, **while waiting**, and **settled**. An action may settle immediately, as selection movement does, or enter a waiting period, as collection and candidate verification do. Each interaction includes a small Mermaid `stateDiagram-v2`.
4. **Variants.** Every document considers the same four axes: input method, panel visibility, snapshot freshness, and Gateway state. The table says what each axis changes when the action starts and what happens if it changes while the action waits.
5. **Cancel and interrupt.** Every document uses these rows in this order:
   - Escape or closing the panel
   - Starting another Clawbar action
   - A scheduled or manual refresh completing
   - Omarchy Shell losing focus, restarting, or exiting
   - The snapshot changing, becoming stale, or becoming unreadable
   - The plugin being disabled, updated, or removed
   - Switching between pointer and keyboard input
   - Gateway resolution or reachability changing
6. **Interactions with other systems.** Every document considers these concerns in this order: privacy boundary; collection and freshness; selection and navigation; notifications and Incidents; theme and accessibility; plugin lifecycle.
7. **Edge cases.** Empty, repeated, boundary, reordered, missing, and first-run cases the user can notice.
8. **Open questions and verification.** What remains to be observed in the running product, suspected defects, assumptions, and the source commit.

The cancel and interrupt rows matter most. They remain identical and in the same order in every interaction document, even when the answer is “no effect.”

### Method

For each document:

1. Read the QML surface in `Clawbar.qml`, `ClawbarPanel.qml`, and the relevant row or detail component.
2. Read `ClawbarLogic.js` for presentation state, selection, labels, freshness, and count behavior.
3. Read the relevant collector module in `scripts/`, then the matching tests. The tests define many boundaries and failure cases more precisely than the interface code alone.
4. Draft the experience from the user's point of view.
5. Exercise ambiguous behavior in the actual Omarchy panel, using the developer demonstration only to provide fictional input states.
6. Record the Clawbar commit checked.

### Verification

Drafting reads the code; verification watches the product. The `verification/` directory contains one checklist per cluster. Each row is one observable claim with setup, steps, expected result, priority, required environment, and a result.

A tester runs the checklists in a real Omarchy Shell with Clawbar enabled. The developer demonstration may create sanitized snapshots, but it does not replace observing panel behavior. A document becomes `verified` only when each P1 and P2 item has passed or has been recorded in `bug-triage.md`.

`bug-triage.md` collects suspected defects from every document, deduplicates them, and records reproduction steps, the likely cause, severity, and the decision needed. Filing issues in the Clawbar source repository is a separate step and requires explicit approval.

### Order of work

1. **Pilot: manual refresh.** A small complete action available from both the bar and panel, with immediate feedback and queued behavior.
2. **Foundations.** The surface and action model, operational model, collection and freshness model, and selection model own the shared terms, state boundaries, numbers, and invariants.
3. **Gateway state and setup.** These are the hardest flows because automatic resolution, collection, Last Known Metadata, fallback verification, and visible severity hand off to one another.
4. **Fleet, Agents, and Automations.** These areas explain the read-only rows and their selected details.
5. **Cross-cutting behavior.** Privacy, notifications, visual presentation, and plugin lifecycle.
6. **Consistency and verification passes.** Align vocabulary and ownership, check links, build checklists, exercise the running product, and collect suspected defects.

Progress is tracked in the [coverage table](#coverage).

### Scope decisions

- **Surface.** The default Clawbar Omarchy bar widget and its panel, for one desktop login and one configured Gateway.
- **Configuration.** The default 30-second refresh interval and default right-bar placement are primary. The accepted custom refresh range is described as a variant.
- **Gateway management is excluded.** Clawbar observes one Gateway and can verify one fallback candidate. Creating, editing, retrying, cancelling, enabling, disabling, or deleting OpenClaw work remains outside Clawbar.
- **Developer demonstration is verification support.** It is not treated as a normal user-facing mode, but its visible `Developer demo` label is documented where relevant.
- **OpenClaw and Tailscale interfaces are boundaries.** Their own setup and behavior are out of scope except for the status and guidance Clawbar exposes.
- **Privacy is documented once and referenced.** Repeating the full allowlist and denial list in every feature would drift.
- **Freshness is documented once and referenced.** The collection foundation owns the 30-second default, 15–300-second range, 12-second deadline, and three-interval stale boundary.
- **Interaction shape.** The unit is an action with the phases ready, invoked, waiting begins, while waiting, and settled. Immediate actions skip the waiting phases. The interrupt list and cross-cutting order are fixed above.
- **Numbered rules.** These are prose documents, not numbered specifications. Stable heading anchors are sufficient for cross-references.

## Structure

```
README.md                              this file
goal.md                                standing instructions for drafting
AGENTS.md, CLAUDE.md                   entry points for agents
glossary.md                            shared vocabulary
bug-triage.md                          suspected defects and decisions

verification/
  README.md                            verification protocol and environment
  bar-and-panel.md                     widget, panel, navigation, and refresh checks
  gateway.md                           resolution, setup, failure, and freshness checks
  operational-rows.md                  Fleet, Agent, and Automation checks
  cross-cutting.md                     privacy, notifications, visuals, and lifecycle checks

foundations/
  surface-and-actions.md               bar, panel, action phases, and fixed interrupts
  operational-model.md                 Gateway, Fleet, Node, Agent, Task, and Automation meanings
  collection-and-freshness.md          scheduling, bounded collection, snapshots, and stale state
  selection-model.md                   one selection across ordered panel rows

bar/
  manual-refresh.md                    middle-click and keyboard refresh behavior; the pilot
  signal-and-tooltip.md                compact severity color and summary text

panel/
  opening-and-closing.md               panel lifecycle and focus
  navigation-and-details.md            row movement, wrapping, selection, scrolling, and detail placement
  empty-and-unavailable-states.md       collecting, no data, empty sections, and unavailable metadata

gateway/
  automatic-resolution.md              local, configured remote, Node-host, and verified fallback precedence
  fallback-setup.md                     candidate listing, selection, verification, errors, and reuse
  health-and-last-known-state.md        healthy, degraded, unstable, offline, configuration error, and stale behavior

fleet/
  nodes.md                              Node rows, deduplication, state, metadata, and selection

agents/
  registration-and-task-results.md      Registered Agent rows and previous Task Result

automations/
  schedules-and-results.md              Automation kinds, timing, enabled state, failures, and details

cross-cutting/
  privacy-boundary.md                   persisted and displayed Operational Metadata and excluded Private Content
  incidents-and-notifications.md        Attention counting, Incident transitions, and grouped notifications
  theme-and-accessibility.md             colors, labels, keyboard access, narrow panels, and reduced motion
  plugin-lifecycle.md                   enable, update, disable, remove, and in-flight collection behavior
```

## Coverage

Status is one of `not started`, `drafted`, or `verified`.

| Document | Status |
| --- | --- |
| glossary.md | drafted |
| bug-triage.md | drafted |
| verification/ (4 checklists) | drafted |
| foundations/surface-and-actions.md | drafted |
| foundations/operational-model.md | drafted |
| foundations/collection-and-freshness.md | drafted |
| foundations/selection-model.md | drafted |
| bar/manual-refresh.md | drafted |
| bar/signal-and-tooltip.md | drafted |
| panel/opening-and-closing.md | drafted |
| panel/navigation-and-details.md | drafted |
| panel/empty-and-unavailable-states.md | drafted |
| gateway/automatic-resolution.md | drafted |
| gateway/fallback-setup.md | drafted |
| gateway/health-and-last-known-state.md | drafted |
| fleet/nodes.md | drafted |
| agents/registration-and-task-results.md | drafted |
| automations/schedules-and-results.md | drafted |
| cross-cutting/privacy-boundary.md | drafted |
| cross-cutting/incidents-and-notifications.md | drafted |
| cross-cutting/theme-and-accessibility.md | drafted |
| cross-cutting/plugin-lifecycle.md | drafted |

## Reference

The source of truth is the Clawbar implementation in this repository, outside `docs/product-description/`, at commit `f08496e`. Those implementation paths are read-only references while this description is written.

- `README.md` and `manifest.json`: installation, requirements, defaults, entry points, and supported surface.
- `CONTEXT.md`: canonical domain vocabulary and distinctions.
- `Clawbar.qml`: bar action, snapshot reading, freshness timer, tooltip, and panel ownership.
- `ClawbarPanel.qml`: visible panel states, keyboard navigation, section headers, scrolling, and candidate actions.
- `RowSection.qml` and the detail-card components: the shared Operational Row list (selection by key, expandable bounded inline row detail) and healthy-label visibility.
- `ClawbarService.qml`: immediate and scheduled collection, coalescing, and candidate-verification serialization.
- `ClawbarLogic.js`: visible states, labels, counts, colors, relative times, and selection reconciliation.
- `scripts/clawbar_collect.py` and the other `scripts/clawbar_*.py` modules: Gateway resolution, bounded metadata collection, privacy reduction, snapshot publication, and Incident transitions.
- `tests/test_clawbar_logic.cjs`: executable specification for the QML-facing presentation model.
- `tests/test_clawbar_collect.py`, `tests/test_clawbar_freshness.py`, `tests/test_clawbar_incidents.py`, and `tests/test_clawbar_automation.py`: executable specifications for collection, freshness, privacy, state transitions, notifications, and Automation behavior.
- `scripts/clawbar_demo.py`: fictional state generator used only for observation in the running product.
