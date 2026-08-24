# Hand verification

The feature documents were written from code and tests. This directory is the protocol for checking them against the running Clawbar panel, one observable claim at a time.

## What is here

| File | Covers |
| --- | --- |
| [bar-and-panel.md](bar-and-panel.md) | `foundations/surface-and-actions.md`, `foundations/selection-model.md`, `bar/*`, and `panel/*` |
| [gateway.md](gateway.md) | `foundations/collection-and-freshness.md` and `gateway/*` |
| [operational-rows.md](operational-rows.md) | `foundations/operational-model.md`, `fleet/*`, `agents/*`, and `automations/*` |
| [cross-cutting.md](cross-cutting.md) | `cross-cutting/*` |

Each table row has a stable ID, priority, required device or condition, a linked claim, precise setup and steps, expected result, and a Result column. Priorities are: **P1** for established facts, shared invariants, and suspected bugs; **P2** for ordinary behavior; **P3** for numbers, colors, layout, and timing.

## How to run a pass

1. Install and enable this checkout with the documented Omarchy plugin command. Use default right-bar placement and a 30-second refresh interval unless the row says otherwise.
2. Confirm the source baseline. The documents cite Clawbar commit `f08496e`; run `git rev-parse --short HEAD`. If implementation files differ, record drift instead of treating every mismatch as a defect.
3. Keep the linked feature document beside the running panel. Use `python scripts/clawbar_demo.py {scenario}` only to establish fictional sanitized state; perform the described pointer and keyboard actions in the real Omarchy panel.
4. Run P1 items across all four files first, then P2, then P3.
5. Replace `—` with `pass`, `fail — {note}`, or `blocked — {reason}`. A fail means the running product differs from the linked claim; it may be a product defect or a documentation error.
6. For every fail, update [`bug-triage.md`](../bug-triage.md). Add the checklist ID to an existing entry or create a new entry only after identifying a code-supported cause.
7. Mark a document `verified` in the [coverage table](../README.md#coverage) only when every P1 and P2 item for it has passed or has been triaged.
8. After a demonstration pass, restore normal collection with `python scripts/clawbar_demo.py --resume`.

## Devices and conditions

- **Mouse:** a real pointer routed through Omarchy Shell. Middle-click must be a physical or compositor-generated middle button, not a normal click.
- **Keyboard:** the panel's real focus target. Synthetic events do not prove shell shortcut or focus behavior.
- **Demo:** a real panel reading a snapshot created by `scripts/clawbar_demo.py`; the script sets state but does not replace observing the UI.
- **Delayed demo:** use the collector fixture or a controlled slow Gateway while keeping the request within 12 seconds. Do not infer responsiveness from a unit test.
- **Tailscale:** at least two online test devices, one with a supported Gateway and one without it. Do not use production devices containing sensitive names.
- **Gateway:** a disposable supported OpenClaw Gateway whose reachability and metadata responses can be controlled.
- **Notification:** a desktop login with `notify-send` and a visible notification daemon; clear existing Clawbar notifications before each case.
- **Screen reader:** the accessibility inspector or screen reader supported by the current Omarchy/Qt environment. Inspect the real accessibility tree.
- **Themes:** `white`, `catppuccin-latte`, `flexoki-light`, and `vantablack`, plus reduced motion where the shell exposes it.
- **Lifecycle:** the documented `omarchy plugin` commands against a disposable installation. Preserve a copy of state before testing removal.
- **Filesystem:** inspect XDG state/runtime paths only after visible behavior is recorded. Do not place Private Content into production OpenClaw data.

## Driving the product from a script

`scripts/clawbar_demo.py` can create the twelve documented fictional states through the same atomic Snapshot seam as the collector. It is suitable for exact setup and for checking bar/panel output, selection, layout, and state transitions. The `Developer demo` prefix must remain visible.

The Python collector fixtures and JavaScript tests can establish failure counts, metadata bounds, reorderings, and private sentinels, but they cannot verify focus, tooltip timing, color contrast, animation, notification rendering, pointer buttons, or screen-reader output. For input claims, use the script only to set state and then use real pointer or keyboard input.

## Results so far

No hand-verification pass has been completed. On 2026-08-24, the source-derived checks passed against the described implementation: 72 Python tests, 20 JavaScript presentation tests, `git diff --check`, and the product-description link checker (30 files, 158 relative links, no broken links). These checks support drafting but do not verify the running interface.

An Omarchy Shell process and Clawbar Snapshot were present, but native interaction could not be authorized: the available computer-use driver refused its inspection tool because that tool had no reviewed risk classification. No pointer, keyboard, tooltip, focus, accessibility-tree, theme, notification, or lifecycle claim was therefore marked as observed. All Result cells remain `—`, every feature document remains `drafted`, and the entries in `bug-triage.md` are code-supported but unconfirmed in the running product.
