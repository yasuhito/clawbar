# Persist operational metadata only

Clawbar stores and displays only bounded Operational Metadata needed to explain Fleet health. It deliberately discards task instructions, message bodies, destinations, account identifiers, host/IP/instance identifiers, and raw errors while parsing OpenClaw output; this makes runtime snapshots and development fixtures safe by construction, at the cost of requiring users to leave Clawbar when they need deeper diagnostic context.
