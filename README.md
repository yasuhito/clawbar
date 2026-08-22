# Clawbar

Clawbar is a private, read-only Omarchy widget for one OpenClaw Gateway.
OpenClaw resolves normal local or configured remote mode first; only an
unavailable normal target triggers active Node host discovery. Clawbar renders
only cached Operational Metadata and never reads, stores, or displays Private
Content.

## Try it locally

```sh
omarchy plugin validate .
ln -s "$PWD" ~/.config/omarchy/plugins/yasuhito.clawbar
omarchy-shell shell rescanPlugins
omarchy plugin enable yasuhito.clawbar
```

Clawbar collects immediately when enabled and every 30 seconds afterward. Node
host discovery and the Gateway probe share one 12-second collection deadline.
Set `CLAWBAR_REFRESH_INTERVAL_SECONDS` to an integer from 15 through 300 before
starting the shell to change that interval. Middle-clicking the widget requests
a non-blocking refresh; overlapping requests are coalesced.
Reachable unsupported JSON is a Configuration Error. A healthy snapshot becomes
Stale when its age exceeds three configured refresh intervals.
The first bounded attempt shows Collecting and becomes No data yet if it produces
no valid snapshot. After a successful collection, one complete collection
failure shows an Unstable Gateway and two consecutive failures show an Offline
Gateway. Both retain the previous Fleet as dimmed, time-stamped Last Known
Metadata without counting historical Node or Automation states as current
Attention Items. A successful collection clears the failure count and restores
current rows. Stale snapshots use the same Last known presentation; their
current yellow Stale state takes precedence over historical row colors.
The panel reads the Gateway-backed `nodes status`, `agents.list`, `tasks.list`,
and paginated `cron.list` JSON surfaces. It immediately reduces Automation data
to ID, name, enabled state, kind, next and last run times, last result, and
consecutive failure count. At most 500 Automations are accepted; larger or
incomplete results make the section unavailable instead of presenting partial
health. Task payloads, destinations, accounts, delivery data, and raw errors
never enter the snapshot.

Fleet Nodes stay in Gateway order. Agent Activity remains separate from the most
recent Task Result. Automations appear in their own section after Agents because
the supported Gateway metadata does not establish Node ownership. Current
Automation failures contribute once to the bar's Attention Item count without
changing Gateway or Node state. Disabled, skipped, event-driven, completed
one-time, and never-run Automations remain non-incident states.

The bar keeps the compact claw mark in the theme foreground, adds a separate
severity point, and shows the Attention Item count when one exists. The panel
uses the same semantic theme roles with a Fleet rail:
circles identify healthy or active state, triangles identify waiting or warning,
diamonds identify current failure, and a dotted ring identifies Disabled
Automation. Last Known Metadata keeps its observed shape with reduced emphasis;
Idle Agent Activity has no point. Labels, text strength, and timestamps preserve
the same distinctions in monochrome themes. The signal board has no
nonessential motion.

Clawbar sends one desktop notification when an Offline Gateway, Offline Node,
Configuration Error, or enabled Automation Failure starts, and one when it
recovers. Changes found in the same collection are grouped. Per-login transition
state lives only under `XDG_RUNTIME_DIR`; repeated collections stay quiet, and a
new desktop login may notify a still-current Incident again. Removing a Node or
Automation from monitoring, or disabling an Automation, ends monitoring
silently. Notifications contain only bounded target labels, generalized states,
and aggregate counts.

Opaque Node UI keys retain selection and expansion across refreshes; the local
key secret and private Node identifiers never enter the snapshot. Automation IDs
remain non-display metadata used only for selection and history. If the local
pseudonymization secret cannot be loaded, Node metadata becomes unavailable
rather than falling back to positional identity.

Press the widget to open the panel. Use `j`, `k`, or the arrow keys to move
focus, Enter to expand or collapse a Node, `r` to refresh, `o` on an Automation
to open its official read-only recent-run history for the collected Gateway
Target, and Escape to close. A connected Gateway with no reported Nodes shows
Empty Fleet; a valid zero-Automation response shows No Automations.
Relative timestamps and the selected row's absolute timestamp update from the
in-memory snapshot without collecting the Gateway again.

Remove the symlink when finished testing. Marketplace installation will use
`omarchy plugin add <repository-url> --enable`.
