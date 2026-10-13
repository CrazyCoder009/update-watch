#!/usr/bin/env bash
# Install update-watch for the current user (no root needed), then run the setup wizard.
# Usage: ./install.sh [--yes]
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
data="${XDG_DATA_HOME:-$HOME/.local/share}/update-watch"
bin="$HOME/.local/bin/update-watch"

if [ "$(id -u)" -eq 0 ]; then
    echo "Please run this as your normal user, not root — update-watch never needs sudo." >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))'; then
    echo "update-watch needs Python 3.8 or newer. Install it with:" >&2
    if   command -v pacman  >/dev/null 2>&1; then echo "  sudo pacman -S python" >&2
    elif command -v apt-get >/dev/null 2>&1; then echo "  sudo apt install python3" >&2
    elif command -v dnf     >/dev/null 2>&1; then echo "  sudo dnf install python3" >&2
    fi
    exit 1
fi

mkdir -p "$data" "$(dirname "$bin")"
rm -rf "$data/update_watch"
cp -r "$here/update_watch" "$data/"
find "$data" -name __pycache__ -prune -exec rm -rf {} +

cat > "$bin" <<LAUNCHER
#!/bin/sh
exec python3 -c 'import sys; sys.path.insert(0, sys.argv.pop(1)); from update_watch.cli import main; sys.exit(main(sys.argv[1:]))' "$data" "\$@"
LAUNCHER
chmod +x "$bin"

echo "Installed update-watch to $data"
echo
exec "$bin" setup "$@"
