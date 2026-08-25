### Repository URL

https://github.com/yasuhito/clawbar

### Category

Widgets

### Tags

ai, bar, quickshell

### Suggest a missing tag

_No response_

### Maintainer notes

Clawbar adds a read-only OpenClaw Fleet signal board to the Omarchy bar. It requires OpenClaw 2026.7.1-2 or a later stable release with the same supported JSON command surfaces and Python 3; the collector uses only the Python standard library. Tailscale is optional and is used only for a verified Gateway fallback when OpenClaw cannot resolve a Gateway. Enabling the plugin starts its bounded collection schedule inside the Omarchy Shell process. Disabling or removing it unloads that scheduler. The plugin installs no systemd units, daemons, or packages.

Reviewer remediation is included in the current repository HEAD: external metadata is rendered as plain text, command output and state files are capped at 8 MiB, and state readers reject non-regular files and final symbolic links.

### Submission checklist

- [x] The repository is public and contains installation and removal instructions.
- [x] I have documented the plugin license and any external dependencies.
- [x] I confirm that I own or have permission to submit this plugin and its preview assets.
- [x] The plugin does not overwrite user configuration without explicit consent.
- [x] I understand that approval is for listing and is not a security review.
