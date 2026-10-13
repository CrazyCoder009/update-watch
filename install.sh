#!/usr/bin/env bash
# Symlink update-watch into ~/.local/bin, fish conf.d and systemd user units.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

mkdir -p ~/.local/bin ~/.config/fish/conf.d ~/.config/systemd/user
ln -sf "$here/bin/update-watch-fetch"  ~/.local/bin/update-watch-fetch
ln -sf "$here/bin/update-watch-status" ~/.local/bin/update-watch-status
ln -sf "$here/fish/update-watch.fish"  ~/.config/fish/conf.d/update-watch.fish
ln -sf "$here/systemd/update-watch.service" ~/.config/systemd/user/update-watch.service
ln -sf "$here/systemd/update-watch.timer"   ~/.config/systemd/user/update-watch.timer

systemctl --user daemon-reload
systemctl --user enable --now update-watch.timer
~/.local/bin/update-watch-fetch || true
echo "Installed. Open a new terminal to see it."
