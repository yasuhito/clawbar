# Clawbar

Clawbar is a private, read-only Omarchy widget for the OpenClaw Nodes you operate.
The first release shows local Gateway health and the count of failed Automations.
It never reads, stores, or displays Private Content.

## Try it locally

```sh
omarchy plugin validate .
ln -s "$PWD" ~/.config/omarchy/plugins/yasuhito.clawbar
omarchy-shell shell rescanPlugins
omarchy plugin enable yasuhito.clawbar
mkdir -p ~/.config/systemd/user
ln -s "$PWD/systemd/clawbar-collect.service" ~/.config/systemd/user/clawbar-collect.service
ln -s "$PWD/systemd/clawbar-collect.timer" ~/.config/systemd/user/clawbar-collect.timer
systemctl --user daemon-reload
systemctl --user enable --now clawbar-collect.timer
```

Remove the symlink when finished testing. Marketplace installation will use
`omarchy plugin add <repository-url> --enable`.
