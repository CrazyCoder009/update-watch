#!/usr/bin/env bash
# Smoke-test install + status + fetch inside real distro containers (needs podman or docker).
# Usage: tests/containers.sh [image ...]   (default: arch, debian, ubuntu, fedora)
set -euo pipefail

engine="$(command -v podman || command -v docker)" || { echo "needs podman or docker" >&2; exit 1; }
src="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
images=("$@")
[ ${#images[@]} -gt 0 ] || images=(archlinux:latest debian:stable ubuntu:24.04 fedora:latest)

for image in "${images[@]}"; do
    echo "=================== $image"
    "$engine" run --rm -v "$src:/src:ro,Z" "$image" bash -euc '
        if command -v pacman >/dev/null; then
            pacman -Syu --noconfirm --needed python fakeroot >/dev/null
        elif command -v apt-get >/dev/null; then
            apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 >/dev/null
            # Make an "upgrade" entry in history.log so the last-update line has data.
            DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq >/dev/null
        else
            dnf install -y -q python3 >/dev/null && dnf makecache -q >/dev/null
        fi
        useradd -m tester
        su tester -c "cd /src && bash install.sh --yes && echo && ~/.local/bin/update-watch doctor"
    '
done
