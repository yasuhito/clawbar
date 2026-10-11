### Repository URL

https://github.com/yasuhito/clawbar

### Category

Widgets

### Tags

ai, bar, quickshell

### Suggest a missing tag

_No response_

### Maintainer notes

Clawbar 0.1.1 adds a read-only OpenClaw status panel to the Omarchy bar. It shows Gateway health, Fleet devices (Nodes), registered Agents and previous Task Results, Automations, and an Incident count. Selecting a device, Agent, or Automation expands its metadata below the row; only one detail is open at a time. Agent presence does not imply activity or health, and offline devices do not count as Incidents. Failed Automations can raise Incidents while the Gateway remains healthy. `preview.png` and the README detail screenshots are captures of the real 0.1.1 panel with live metadata. It requires OpenClaw 2026.7.1-2 or a later stable release with the same supported JSON command surfaces and Python 3; the collector uses only the Python standard library. Tailscale is optional and is used only for a verified Gateway fallback when OpenClaw cannot resolve a Gateway. Enabling the plugin starts its bounded collection schedule inside the Omarchy Shell process. Disabling or removing it unloads that scheduler. The plugin installs no systemd units, daemons, or packages.

Reviewer remediation is included in version 0.1.1: external metadata is rendered as plain text; command output, state files, and theme-color reads are capped at 8 MiB; and file readers reject non-regular files and final symbolic links. QML routes both the Snapshot and theme colors through these bounded collector interfaces.

Future updates use `omarchy plugin update io.github.yasuhito.clawbar --yes`. This command does not restart Omarchy Shell. If the old version stays loaded, run `omarchy restart shell`.

### Submission checklist

- [x] The repository is public and contains installation and removal instructions.
- [x] I have documented the plugin license and any external dependencies.
- [x] I confirm that I own or have permission to submit this plugin and its preview assets.
- [x] The plugin does not overwrite user configuration without explicit consent.
- [x] I understand that approval is for listing and is not a security review.
