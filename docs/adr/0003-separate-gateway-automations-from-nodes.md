# Separate Gateway Automations from Nodes

OpenClaw's supported Automation JSON surface does not establish Node ownership, so Clawbar presents Automations in an independent section after Agents instead of assigning them to Fleet Nodes. An Automation Failure remains on its Automation row and contributes once to the bar and Incident state without changing Gateway or Node state; unavailable Automation metadata degrades only the Gateway.

The collector reads the full Automation response to retain consecutive failure counts, immediately reduces it through an explicit Operational Metadata allowlist, and never persists or displays payloads, destinations, raw errors, or other Private Content. Clawbar accepts at most 500 Automations per collection; larger results make the section unavailable rather than presenting incomplete health as current.
