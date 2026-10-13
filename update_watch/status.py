"""`update-watch status`: the block printed when a terminal opens.

Reads only local files (logs + cache). If the cache is stale it starts a
background `fetch` and returns immediately.
"""
import os
import subprocess
import sys
import time

from .config import LOCK_FILE, load_state
from .distro import get_backend
from .estimate import estimate_seconds
from .util import Colour, ago, from_iso, hours_since, human_duration, human_size

LOCK_MAX_AGE_H = 0.33  # a fetch normally takes < 1 min; older locks are leftovers


def _spawn_fetch():
    try:
        if os.path.exists(LOCK_FILE) and (time.time() - os.path.getmtime(LOCK_FILE)) / 3600 < LOCK_MAX_AGE_H:
            return
        with open(LOCK_FILE, "w") as f:
            f.write("spawning")
        pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ, PYTHONPATH=pkg_parent)
        subprocess.Popen([sys.executable, "-m", "update_watch", "fetch", "--quiet"], env=env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def status(cfg):
    c = Colour()
    state = load_state()
    backend = get_backend(cfg["family"])

    last = backend.last_upgrade()
    cached = from_iso(state.get("last_upgrade_full"))
    if cached and (last is None or cached > last):
        last = cached

    # 1. Last update
    if last is None:
        print(f" {c.yellow}Last update: unknown (no system upgrade found in the package manager logs){c.reset}")
    else:
        text, days = ago(last)
        colour = c.green if days < 7 else c.yellow if days < 14 else c.red
        print(f" {c.bold}Last update:{c.reset} {last.astimezone():%a %d %b %Y, %H:%M}  {colour}({text}){c.reset}")

    # 2. Pending updates
    pending = state.get("pending") or {}
    checked = from_iso(pending.get("checked"))
    fresh = checked is not None and (last is None or checked > last)
    stale = (hours_since(from_iso(state.get("last_fetch"))) > cfg["refresh_hours"]) or not fresh
    if fresh and "count" in pending:
        print(" " + _pending_line(c, cfg, state, backend, pending, checked))
    elif pending.get("error"):
        print(f" {c.dim}Update check failed: {pending['error']}{c.reset}")
    else:
        print(f" {c.dim}Checking for updates in the background…{c.reset}")
    if pending.get("lists_age_hours", 0) > 72:
        print(f" {c.yellow}Package lists are {pending['lists_age_hours'] / 24:.0f} days old "
              f"(is apt-daily.timer disabled?){c.reset}")

    # 3. News since the last update
    _news(c, cfg, state, last)

    if stale:
        _spawn_fetch()


def _pending_line(c, cfg, state, backend, p, checked):
    aur = p.get("aur") or 0
    if not p["count"] and not aur:
        return f"{c.green}✓ Up to date{c.reset} {c.dim}(checked {_short_ago(checked)}){c.reset}"
    parts = [f"{c.bold}{p['count']} update{'s' if p['count'] != 1 else ''} waiting{c.reset}"]
    if p.get("download") is not None:
        parts.append(f"{human_size(p['download'])} download")
    if p.get("install_delta") is not None:
        sign = "+" if p["install_delta"] >= 0 else ""
        parts.append(f"{sign}{human_size(p['install_delta'])} on disk")
    secs = estimate_seconds(state.get("history", []), p["count"], p.get("download") or 0,
                            backend.history_includes_download, cfg["download_mb_per_s"])
    if secs:
        parts.append(f"{human_duration(secs)} to install")
    if aur:
        parts.append(f"+{aur} AUR")
    sep = f" {c.dim}·{c.reset} "
    return sep.join(parts)


def _short_ago(d):
    h = hours_since(d)
    if h < 1:
        return f"{max(1, int(h * 60))} min ago"
    if h < 48:
        return f"{int(h)} h ago"
    return f"{int(h / 24)} days ago"


def _news(c, cfg, state, last):
    news = state.get("news")
    if not news:
        return
    ok = from_iso(news.get("last_fetch_ok"))
    if hours_since(ok) > 24 and state.get("last_fetch"):
        print(f" {c.yellow}News feeds haven't refreshed in over a day (update-watch doctor){c.reset}")
    new = [i for i in news.get("items", [])
           if last is None or (from_iso(i["date"]) and from_iso(i["date"]) > last)]
    if not new:
        return
    flagged = sum(1 for i in new if i.get("important"))
    head = f"{len(new)} news item{'s' if len(new) != 1 else ''} since your last update"
    if flagged:
        print(f" {c.red}{c.bold}⚠ {head} ({flagged} flagged) — read before updating:{c.reset}")
    else:
        print(f" {c.cyan}ℹ {head}:{c.reset}")
    shown = new[:cfg["max_news"]]
    width = max(len(i["source"]) for i in shown)
    for i in shown:
        mark = f"{c.red}!{c.reset}" if i.get("important") else " "
        date = from_iso(i["date"]).astimezone()
        print(f"  {mark} {c.dim}[{i['source']:<{width}}] {date:%Y-%m-%d}{c.reset}  {i['title']}")
        if i.get("link"):
            print(f"      {c.dim}{i['link']}{c.reset}")
    if len(new) > len(shown):
        print(f"    {c.dim}…and {len(new) - len(shown)} more{c.reset}")
