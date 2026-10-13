#!/usr/bin/env bash
set -uo pipefail
systemctl --user disable --now update-watch.timer 2>/dev/null
rm -f ~/.local/bin/update-watch-fetch ~/.local/bin/update-watch-status \
      ~/.config/fish/conf.d/update-watch.fish \
      ~/.config/systemd/user/update-watch.service ~/.config/systemd/user/update-watch.timer
systemctl --user daemon-reload
rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/update-watch"
echo "Uninstalled."
