"""Interactive `setup`, `uninstall` and `doctor`."""
import os
import shutil
import sys

from . import shells
from .config import (BIN, CACHE_DIR, CONFIG_DIR, DATA_DIR, HOME, config_exists, load_config, load_state,
                     save_config)
from .distro import FAMILIES, detect_family, get_backend, os_release, pretty_name
from .news import CATALOG, default_feeds
from .util import Colour, from_iso, run

SYSTEMD_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "systemd", "user")
SERVICE = """[Unit]
Description=update-watch: check for updates and distro news
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=%h/.local/bin/update-watch fetch --quiet
"""
TIMER = """[Unit]
Description=update-watch: refresh every {hours} hours

[Timer]
OnBootSec=2min
OnUnitActiveSec={hours}h
Persistent=true

[Install]
WantedBy=timers.target
"""
PKG_HINT = {"arch": "sudo pacman -S {}", "debian": "sudo apt install {}", "fedora": "sudo dnf install {}"}

c = Colour()


class Prompter:
    def __init__(self, assume_yes):
        self.yes = assume_yes or not sys.stdin.isatty()

    def ask(self, question, default=""):
        if self.yes:
            return default
        try:
            answer = input(f"{question} {c.dim}[{default}]{c.reset} " if default else f"{question} ").strip()
        except EOFError:
            return default
        return answer or default

    def confirm(self, question, default=True):
        answer = self.ask(f"{question} ({'Y/n' if default else 'y/N'})", "")
        return default if not answer else answer.lower().startswith("y")

    def checklist(self, title, options, allow_url=False):
        """options: list of [label, selected, payload]. Returns payloads of selected options."""
        while True:
            print(f"\n{c.bold}{title}{c.reset}")
            for n, (label, selected, _) in enumerate(options, 1):
                print(f"  {n:>2}. [{'x' if selected else ' '}] {label}")
            if self.yes:
                break
            hint = "numbers to toggle" + (", a feed URL to add" if allow_url else "") + ", Enter to continue"
            answer = self.ask(f"{c.cyan}›{c.reset} ({hint}):")
            if not answer:
                break
            if allow_url and answer.startswith(("http://", "https://")):
                name = self.ask("  Name for this feed:", "Custom")
                options.append([f"{name} — {answer}", True, {"name": name, "url": answer}])
                continue
            for token in answer.replace(",", " ").split():
                if token.isdigit() and 1 <= int(token) <= len(options):
                    options[int(token) - 1][1] = not options[int(token) - 1][1]
        return [payload for _, selected, payload in options if selected]


def systemd_user_available():
    if not shutil.which("systemctl"):
        return False
    rc, _ = run(["systemctl", "--user", "show-environment"], timeout=10)
    return rc == 0


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.islink(path):  # replace v1 symlinks instead of writing through them
        os.remove(path)
    with open(path, "w") as f:
        f.write(text)


def install_timer(hours):
    _write(os.path.join(SYSTEMD_DIR, "update-watch.service"), SERVICE)
    _write(os.path.join(SYSTEMD_DIR, "update-watch.timer"), TIMER.format(hours=hours))
    run(["systemctl", "--user", "daemon-reload"], timeout=30)
    rc, _ = run(["systemctl", "--user", "enable", "--now", "update-watch.timer"], timeout=30)
    return rc == 0


def remove_timer():
    if shutil.which("systemctl"):
        run(["systemctl", "--user", "disable", "--now", "update-watch.timer"], timeout=30)
    for name in ("update-watch.service", "update-watch.timer"):
        path = os.path.join(SYSTEMD_DIR, name)
        if os.path.lexists(path):
            os.remove(path)
    if shutil.which("systemctl"):
        run(["systemctl", "--user", "daemon-reload"], timeout=30)


def remove_v1_leftovers():
    for name in ("update-watch-fetch", "update-watch-status"):
        path = os.path.join(HOME, ".local", "bin", name)
        if os.path.islink(path):
            os.remove(path)
    old_cache = os.path.join(CACHE_DIR, "news.json")
    if os.path.exists(old_cache):
        os.remove(old_cache)


def setup(assume_yes=False):
    p = Prompter(assume_yes)
    existing = config_exists()
    cfg = load_config()
    info = os_release()

    print(f"{c.bold}update-watch setup{c.reset}\n")
    family = cfg.get("family") or detect_family(info)
    print(f"Detected {c.bold}{pretty_name(info)}{c.reset} → {family or 'unsupported'} family")
    if family not in FAMILIES or not p.confirm("Is that right?"):
        if p.yes and family not in FAMILIES:
            print("Unsupported distro (supported: Arch, Debian/Ubuntu and Fedora families).")
            return 1
        choice = p.ask(f"Which family is your distro based on? ({'/'.join(FAMILIES)})", family or "")
        if choice not in FAMILIES:
            print("Unsupported distro family, aborting.")
            return 1
        family = choice
    cfg["family"] = family
    backend = get_backend(family)

    missing = backend.missing_tools()
    for tool, hint in missing:
        print(f"{c.yellow}! Missing '{tool}' — needed to check pending updates. Install: "
              f"{PKG_HINT[family].format(hint)}{c.reset}")

    # News feeds
    chosen_urls = {f["url"] for f in cfg["feeds"]} if existing else {f["url"] for f in default_feeds(info)}
    options = [[f"{feed['name']:<14} {c.dim}{feed['url']}{c.reset}", feed["url"] in chosen_urls,
                {k: v for k, v in feed.items() if k in ("name", "url", "flag_all")}]
               for feed in CATALOG.values()]
    for feed in cfg["feeds"]:
        if feed["url"] not in {f["url"] for f in CATALOG.values()}:
            options.append([f"{feed['name']:<14} {c.dim}{feed['url']}{c.reset}", True, feed])
    cfg["feeds"] = p.checklist("News feeds to watch:", options, allow_url=True)

    # Shells
    login = shells.login_shell()
    installed = shells.available()
    preselect = set(cfg["shells"]) if existing else {login} if login in installed else set(installed[:1])
    shell_opts = [[f"{s}{' (your login shell)' if s == login else ''}", s in preselect, s] for s in installed]
    cfg["shells"] = p.checklist("Show the update summary when these shells start:", shell_opts)

    # Download speed only matters where the logs don't include download time.
    if not backend.history_includes_download:
        speed = p.ask("\nRoughly how fast is your internet, in MB/s? (for the time estimate)",
                      str(cfg["download_mb_per_s"]))
        try:
            cfg["download_mb_per_s"] = max(0.1, float(speed))
        except ValueError:
            pass

    print()
    remove_v1_leftovers()
    for s in shells.SHELLS:
        if s in cfg["shells"]:
            print(f"✓ Hooked into {s}: {shells.install(s)}")
        elif shells.is_installed(s):
            shells.uninstall(s)
            print(f"✓ Removed hook from {s}")

    if systemd_user_available() and install_timer(cfg["refresh_hours"]):
        cfg["scheduler"] = "systemd"
        print(f"✓ systemd user timer enabled (refreshes every {cfg['refresh_hours']} h)")
    else:
        cfg["scheduler"] = "none"
        print("✓ No systemd user session: will refresh in the background when a terminal opens")
    save_config(cfg)
    print(f"✓ Config saved to {CONFIG_DIR}/config.json")

    print("\nChecking for updates and news now (can take a minute)…")
    from .fetch import fetch
    fetch(cfg, quiet=True)
    print()
    from .status import status
    status(cfg)
    print(f"\n{c.green}Done!{c.reset} Open a new terminal to see this automatically.")
    print(f"{c.dim}Change settings: update-watch setup · remove: update-watch uninstall{c.reset}")
    if os.path.dirname(BIN) not in os.environ.get("PATH", "").split(os.pathsep):
        print(f"{c.dim}Tip: add ~/.local/bin to your PATH to run 'update-watch' by name.{c.reset}")
    return 0


def uninstall(assume_yes=False):
    p = Prompter(assume_yes)
    if not p.yes and not p.confirm("Remove update-watch, its shell hooks, timer, config and cache?", False):
        return 1
    for s in shells.SHELLS:
        shells.uninstall(s)
    remove_timer()
    remove_v1_leftovers()
    for path in (CONFIG_DIR, CACHE_DIR, DATA_DIR):
        shutil.rmtree(path, ignore_errors=True)
    if os.path.lexists(BIN):
        os.remove(BIN)
    print("update-watch removed. Open shells keep working; new ones won't show it.")
    return 0


def doctor():
    cfg = load_config()
    state = load_state()
    info = os_release()
    family = cfg.get("family") or detect_family(info)
    print(f"Distro:     {pretty_name(info)} ({family})")
    print(f"Config:     {CONFIG_DIR}/config.json {'(missing — run setup)' if not config_exists() else ''}")
    print(f"Scheduler:  {cfg['scheduler']}")
    if cfg["scheduler"] == "systemd":
        rc, out = run(["systemctl", "--user", "is-active", "update-watch.timer"], timeout=10)
        print(f"Timer:      {out.strip() or 'unknown'}")
    print(f"Shells:     {', '.join(cfg['shells']) or 'none'}")
    print(f"Feeds:      {', '.join(f['name'] for f in cfg['feeds']) or 'none'}")
    if family in FAMILIES:
        backend = get_backend(family)
        for tool, hint in backend.missing_tools():
            print(f"Missing:    {tool} ({hint})")
        print(f"Last upgrade (logs): {backend.last_upgrade(full=True)}")
        print(f"Upgrades in history: {len(backend.history())}")
    print(f"Last fetch: {from_iso(state.get('last_fetch')) or 'never'}")
    for e in (state.get("news") or {}).get("errors", []):
        print(f"Feed error: {e}")
    if (state.get("pending") or {}).get("error"):
        print(f"Update check error: {state['pending']['error']}")
    return 0
