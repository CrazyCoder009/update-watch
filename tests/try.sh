#!/usr/bin/env bash
# Try update-watch without touching your real setup:
# installs it into a throwaway HOME and opens your shell there.
# Exit that shell and everything is deleted again.
# Usage: tests/try.sh [bash|zsh|fish] [--yes]
set -euo pipefail

src="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
shell="$(basename "${SHELL:-bash}")"
case "${1:-}" in bash|zsh|fish) shell="$1"; shift ;; esac

sandbox="$(mktemp -d -t update-watch-try.XXXXXX)"
trap 'rm -rf -- "$sandbox"' EXIT

echo "Sandbox HOME: $sandbox (deleted when you exit)"
echo
env HOME="$sandbox" XDG_CONFIG_HOME="$sandbox/.config" XDG_CACHE_HOME="$sandbox/.cache" \
    XDG_DATA_HOME="$sandbox/.local/share" UPDATE_WATCH_NO_TIMER=1 SHELL="$(command -v "$shell")" \
    bash "$src/install.sh" "$@"

echo
echo "Opening $shell with the sandbox HOME. Type 'exit' to leave and clean up."
echo "Try: update-watch · update-watch news · update-watch demo · update-watch doctor"
echo
env HOME="$sandbox" XDG_CONFIG_HOME="$sandbox/.config" XDG_CACHE_HOME="$sandbox/.cache" \
    XDG_DATA_HOME="$sandbox/.local/share" PATH="$sandbox/.local/bin:$PATH" \
    "$shell" -i || true
