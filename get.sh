#!/usr/bin/env bash
# One-line installer for update-watch:
#   curl -fsSL https://raw.githubusercontent.com/CrazyCoder009/update-watch/main/get.sh | bash
# Pass options after `bash -s --`, e.g. `| bash -s -- --yes` to skip the questions.
set -euo pipefail

# Everything is inside main() so a half-downloaded script never runs.
main() {
    local repo="${UPDATE_WATCH_REPO:-CrazyCoder009/update-watch}"
    local ref="${UPDATE_WATCH_REF:-main}"
    local tmp
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT

    echo "Downloading update-watch ($repo@$ref)…"
    curl -fsSL "https://github.com/$repo/archive/$ref.tar.gz" | tar -xz -C "$tmp" --strip-components=1

    # stdin is this script when piped from curl, so give the wizard the terminal.
    if [ -t 1 ] && { : </dev/tty; } 2>/dev/null; then
        bash "$tmp/install.sh" "$@" </dev/tty
    else
        bash "$tmp/install.sh" --yes "$@"
    fi
}

main "$@"
