# Schedule bounded collection through one OpenClaw Gateway

Clawbar reads only an atomically replaced snapshot from QML; it never waits for OpenClaw commands during rendering. A lightweight Quickshell service timer launches a separate bounded collector process every configured refresh interval because Omarchy's standard plugin installer does not run install or removal hooks for systemd units.

The collector connects to exactly one Gateway. It first delegates resolution to the local OpenClaw CLI and configuration: local mode resolves to loopback, remote mode uses `gateway.remote.url`, and a Node host keeps Gateway connection metadata in OpenClaw-owned state. Clawbar does not ask the user to choose a host when OpenClaw already identifies one. If no local process, remote configuration, or node-host metadata identifies a Gateway, the UI may enumerate Tailscale devices as fallback candidates and let the user choose one device to verify. A Tailscale device is not accepted as a Gateway until the supported OpenClaw command surface responds. Clawbar never connects to individual Nodes or fans out concurrent Node probes. The Gateway supplies the Fleet, Agent, Task, and Automation metadata.

This replaces the earlier direct multi-Node collection model.

When collection freshness is lost, Clawbar retains the prior Fleet only as Last Known Metadata. The retained rows preserve their last observed state while reduced emphasis, the `Last known` label, and a relative timestamp communicate freshness separately; historical rows do not establish current Incidents or contribute to current Attention counts. A Stale Snapshot is therefore the current yellow state even when the retained Fleet includes muted Offline Nodes. This preserves diagnostic context without presenting old observations as current health.

Disabling or removing the plugin stops scheduling immediately, while an already running collection exits within its 12-second deadline. The collector owns per-login Incident transition state and emits each failure or recovery notification once. QML remains the display and interaction surface; it shows the fallback device picker only when OpenClaw cannot resolve a Gateway itself.
