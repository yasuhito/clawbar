# Goal: complete the Clawbar product description

You are working in `docs/product-description/` inside the Clawbar repository. Read `README.md`, `glossary.md`, `foundations/surface-and-actions.md`, and `bar/manual-refresh.md` first. The README defines the purpose, template, method, structure, and coverage table. The other files are exemplars once they exist; match their depth, tone, vocabulary, and structure.

## Source of truth

The Clawbar implementation is in the repository root, two directories above this file. Treat every path outside `docs/product-description/` as read-only while writing these documents. Describe the default enabled Omarchy bar widget and panel, connected to one Gateway, at source commit `f08496e`. The developer demonstration is verification support rather than a normal product mode. OpenClaw administration, Tailscale administration, and control of Nodes, Tasks, Agents, or Automations are outside scope.

Read in this order before drafting:

1. `CONTEXT.md` for canonical vocabulary and distinctions.
2. `Clawbar.qml`, `ClawbarPanel.qml`, and the relevant row or detail QML component for the visible action and state.
3. `ClawbarLogic.js` for selection, visible state, labels, severity, counts, time display, and freshness.
4. `ClawbarService.qml` and the relevant module under `scripts/` for scheduling, resolution, reduction, publication, or notification behavior.
5. The matching tests. Start with `tests/test_clawbar_logic.cjs`, then use `tests/test_clawbar_collect.py`, `tests/test_clawbar_freshness.py`, `tests/test_clawbar_incidents.py`, or `tests/test_clawbar_automation.py` as the feature requires.
6. `README.md`, `manifest.json`, and `scripts/clawbar_demo.py` for documented defaults and the running-product verification route.

Do not describe code. Describe what the user sees and does. Technical detail goes only in `> Technical note:` block quotes and only when it changes what the user would expect.

## Writing rules

- Follow the README's eight-section template for every interaction document. Foundations and cross-cutting documents may adapt sections that do not apply, but every real Action must cover the fixed variants and fixed interrupt list.
- The Action phases are ready, invoked, waiting begins, while waiting, and settled. Immediate Actions explicitly skip the waiting phases.
- Every variants table uses these rows in order: input method; panel visibility; snapshot freshness; Gateway state.
- Every cancel-and-interrupt table uses these rows in order: Escape or closing the panel; starting another Clawbar Action; a scheduled or manual refresh completing; Omarchy Shell losing focus, restarting, or exiting; the snapshot changing, becoming stale, or becoming unreadable; the plugin being disabled, updated, or removed; switching between pointer and keyboard input; Gateway resolution or reachability changing.
- Every interactions section uses these concerns in order: privacy boundary; collection and freshness; selection and navigation; notifications and Incidents; theme and accessibility; plugin lifecycle.
- Use glossary terms exactly. Add a full glossary definition before introducing a necessary new term. Do not coin synonyms.
- Use sentence case for headings and direct, concrete language. Avoid hedging and marketing.
- State surprising behavior plainly. Put suspected defects in “Open questions and verification” rather than smoothing them over.
- Link to the foundation that owns shared facts rather than repeating it. `foundations/collection-and-freshness.md` owns intervals, deadline, snapshot transition, and stale timing. `foundations/selection-model.md` owns ordering, stable keys, reconciliation, wrapping, and one-detail behavior.
- End each document with `## Open questions and verification`, then bullets, then `Verified against Clawbar commit \`f08496e\`.`
- Include one Mermaid `stateDiagram-v2` for each Action. Show only user-observable states and label transitions with the input and visible outcome.

## Things already established (do not re-derive, do not contradict)

This section starts with facts established during scope and grows as foundations are written.

- Clawbar is read-only. It observes one Gateway and cannot control Nodes, Agents, Tasks, or Automations.
- The default refresh interval is 30 seconds. Accepted configured values are whole seconds from 15 through 300; invalid values use the 30-second default.
- One whole collection has a 12-second deadline.
- A snapshot becomes stale only after its age exceeds three accepted refresh intervals; at exactly three intervals it remains in its recorded state.
- A scheduled collection starts immediately when the service loads and then repeats at the configured interval.
- Manual refresh does not block the bar or panel. Repeated refresh requests while busy coalesce into one pending refresh.
- One candidate-verification request may wait behind a busy collection. A later pending candidate replaces the earlier pending candidate; refresh remains one coalesced pending request.
- Current metadata and Last Known Metadata are different. Historical rows never establish current Incidents or carry forward their old Attention count.
- One failed collection after prior success produces Unstable Gateway; two consecutive failures produce Offline Gateway. An initial failure with no prior success produces No data.
- Gateway Setup Required is warning-colored but is not an Incident and contributes zero Attention Items.
- Offline Node is muted Operational Metadata, not an Attention Item or Incident.
- Registered Agent and Task Result are independent; neither claims current activity.
- Automations are independent of Nodes. An enabled Automation Failure creates one Attention Item; disabled or skipped Automations do not.
- The panel has one selection across Gateway candidates, Nodes, Agents, and Automations. Stable keys retain selection across reordered snapshots; if the selected row disappears, selection stays near its prior index.
- The documents use `Gateway`, `Gateway Target`, `Fleet`, `Node`, `Registered Agent`, `Task Result`, `Automation`, `Attention Item`, `Incident`, `Operational Metadata`, and `Private Content` as defined in the glossary and source `CONTEXT.md`.

## Order of work

1. Write `bar/manual-refresh.md` as the pilot and iterate until it fixes the template, tone, and depth.
2. Write the foundations in this order: `surface-and-actions.md`, `operational-model.md`, `collection-and-freshness.md`, `selection-model.md`. Add their load-bearing facts to this file.
3. Read all Gateway resolution, collection, snapshot, freshness, and panel setup behavior before writing the three `gateway/` documents. `automatic-resolution.md` owns target precedence; `fallback-setup.md` owns candidate interaction and verification; `health-and-last-known-state.md` owns visible Gateway state and historical handoff.
4. Write the remaining bar, panel, Fleet, Agent, Automation, and cross-cutting documents. They may be drafted in parallel only after the pilot and foundations exist. Review every result against the glossary and established facts.
5. Run a consistency pass: one owner for each behavior, shared terms used identically, interrupt rows and concern order fixed, every relative link and heading valid, every document with a footer, and README structure matching files.
6. Create verification checklists and `bug-triage.md`. Run what can be observed in the actual Omarchy panel, record what the pass did not cover, and never mark a document verified from automated checks alone.

## Working rules

- Commit each document or coherent group with `docs: add {path}` or `docs: revise {path}`. Use Conventional Commits and no AI attribution.
- Never modify Clawbar implementation files outside `docs/product-description/`; they are read-only sources for this work.
- Update README structure and coverage before adding, splitting, merging, or removing a planned document.
- When code and tests do not determine a behavior, document what is known, put the rest in open questions, and continue. Do not guess.
- The pilot should be about 150–200 lines. Gateway documents may be longer; static cross-cutting documents may be shorter. Completeness matters more than length.
- Update coverage to `drafted` when a document lands. Use `verified` only after the manual verification rule is satisfied.

The project is complete when the coverage table has no `not started` rows, links pass, the consistency review is complete, checklists exist, observed results are recorded, and suspected defects are deduplicated in `bug-triage.md`.
