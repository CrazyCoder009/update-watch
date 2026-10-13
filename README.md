# update-watch

A small, no-root helper that greets every new terminal with:

- **when you last updated** your system, with the date, time and how many days ago
- **what's waiting**: number of updates, download size, change in disk use, and a rough install time learned from your own past upgrades
- **news posted since your last update** from your distro (Arch News, CachyOS, Fedora Common Issues, Ubuntu announcements…), with likely-breaking items flagged in red, so you can read them *before* you update

```
 Last update: Fri 09 Oct 2026, 21:59  (4 days ago)
 194 updates waiting · 522 MB download · +3.0 MB on disk · ~7 min to install · +2 AUR
 ⚠ 1 news item since your last update (1 flagged) — read before updating:
  ! [Arch] 2026-10-11  foo >= 2.0 requires manual intervention
      https://archlinux.org/news/...
```

Works on **Arch** (Arch, CachyOS, EndeavourOS, Manjaro…), **Debian** (Debian, Ubuntu, Mint, Pop!_OS…) and **Fedora** (Fedora, Nobara, RHEL clones) families, in **bash, zsh and fish**.
It only reads and reports. It never installs updates and never needs sudo.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB_USER/update-watch/main/get.sh | bash
```

Prefer to look before you run? Do this instead:

```sh
git clone https://github.com/YOUR_GITHUB_USER/update-watch
cd update-watch
./install.sh
```

The setup wizard detects your distro and shell, lets you pick news feeds (sensible ones are pre-ticked), and asks for your rough download speed. Add `--yes` to accept all defaults without questions.

Requirements: Python 3.8+ (already present on most desktops). On Arch, `fakeroot` is also needed to check pending updates without root.

## Commands

| command | what it does |
|---|---|
| `update-watch` | print the summary (this is what runs when a terminal opens) |
| `update-watch fetch` | refresh news and pending updates now |
| `update-watch setup` | re-run the wizard to change feeds, shells or speed |
| `update-watch doctor` | show the detected distro, config and recent errors |
| `update-watch uninstall` | remove everything (hooks, timer, config, cache) |

## How it works

- **Terminal start is cached and fast (~0.1 s).** The summary only reads local logs and a cache file. A systemd user timer refreshes the cache every 3 hours. Without systemd, a refresh starts in the background when the cache is stale.
- **Last update** comes from the package manager's own records:
  - Arch: `/var/log/pacman.log`, using only `-Syu` runs that actually upgraded something
  - Debian: `/var/log/apt/history.log*`, including unattended-upgrades
  - Fedora: the dnf5/dnf4 history databases, including GNOME Software updates
- **Pending updates and sizes** are checked without root:
  - Arch: a private copy of the sync databases (the same approach as `checkupdates`), plus `paru`/`yay -Qua` for AUR updates
  - Debian: `apt-get -s`, using the package lists that `apt-daily.timer` keeps fresh
  - Fedora: `dnf repoquery --upgrades`, using the metadata that `dnf-makecache.timer` keeps fresh
- **Time estimate** is the median seconds per package from your last ~10 upgrades, multiplied by the number of pending packages. Debian and Fedora also add download size ÷ your speed, because their logs don't include download time. This is a rough guide only.
- **News** comes from RSS/Atom feeds. An item is flagged when its title mentions things like *manual intervention*, *requires*, *boot*, *nvidia*, *regression* or *compromised*. Every Fedora Common Issues post is flagged.

Files: `~/.local/share/update-watch` (code), `~/.local/bin/update-watch`, `~/.config/update-watch/config.json`, `~/.cache/update-watch/`.

## Development

```sh
python3 -m unittest -v          # unit tests with sample logs for every distro family
tests/containers.sh             # install + run inside Arch/Debian/Ubuntu/Fedora containers (podman or docker)
```

Before publishing, replace `YOUR_GITHUB_USER` in `get.sh` and this README.

## License

MIT
