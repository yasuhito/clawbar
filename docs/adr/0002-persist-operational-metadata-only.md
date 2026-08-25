# Persist operational metadata only

Clawbar stores and displays only bounded Operational Metadata needed to explain Fleet health. It deliberately discards task instructions, message bodies, destinations, account identifiers, host/IP/instance identifiers, and raw errors while parsing OpenClaw output; this makes runtime snapshots and development fixtures safe by construction, at the cost of requiring users to leave Clawbar when they need deeper diagnostic context.

The boundary is enforced before parsing and rendering as well as after it. Each command stream and local file read has an 8 MiB limit. File readers accept only regular files and do not follow a final symbolic link. QML obtains both the cache and current theme colors through the bounded collector interface and renders every displayed value as plain text, preventing external metadata or theme files from becoming an unbounded read or a rich-text/resource request.
