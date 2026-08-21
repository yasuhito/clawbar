# Clawbar

Clawbar is a private, read-only Omarchy widget for the single OpenClaw Gateway
resolved from local configuration, configured remote mode, or an active Node
host service. It renders only cached Operational Metadata and never reads,
stores, or displays Private Content.

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
starting the shell to change that interval. Pressing the widget requests a
non-blocking refresh; overlapping requests are coalesced.

Remove the symlink when finished testing. Marketplace installation will use
`omarchy plugin add <repository-url> --enable`.
