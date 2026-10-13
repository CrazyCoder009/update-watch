"""The compact greeting printed when a terminal opens, plus `news` and `demo`.

    ● Updated 4 days ago (Fri 09 Oct, 21:59) · ▲ 194 pending (522 MB, ~7 min) · ⚠ 1 news
      ! Arch     11 Oct  foo >= 2.0 requires manual intervention

Reads only local files (logs + cache). If the cache is stale it starts a
background `fetch` and returns immediately.
"""
import os
import shutil
import subprocess
import sys
import time
from datetime import timedelta

from .config import LOCK_FILE, load_state
from .distro import get_backend
from .estimate import estimate_seconds
from .util import Colour, ago, from_iso, hours_since, human_duration, human_size, now, visible_len

LOCK_MAX_AGE_H = 0.33  # a fetch normally takes < 1 min; older locks are leftovers
INDENT = "   "


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


def last_upgrade(backend, state):
    last = backend.last_upgrade()
    cached = from_iso(state.get("last_upgrade_full"))
    return cached if cached and (last is None or cached > last) else last


def pending_is_fresh(state, last):
    checked = from_iso((state.get("pending") or {}).get("checked"))
    return checked is not None and (last is None or checked > last)


def news_since(state, last):
    items = (state.get("news") or {}).get("items", [])
    return [i for i in items if last is None or (from_iso(i["date"]) and from_iso(i["date"]) > last)]


def hyperlinks_enabled(cfg, c):
    return (bool(c.reset) and cfg.get("hyperlinks", True) and not os.environ.get("NO_HYPERLINKS")
            and os.environ.get("TERM") != "linux")


def link(text, url, enabled):
    if not enabled or not url:
        return text
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def truncate(text, width):
    if width <= 1:
        return "…" if text else ""
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"


def wrap_segments(segments, width, c):
    """Join segments with ' · ', breaking onto indented lines instead of overflowing."""
    sep = f" {c.dim}·{c.reset} "
    lines, line = [], " "
    for seg in segments:
        candidate = line + (sep if line.strip() else "") + seg
        if line.strip() and visible_len(candidate) > width:
            lines.append(line)
            line = INDENT + seg
        else:
            line = candidate
    lines.append(line)
    return lines


def render(cfg, state, last, includes_download, width, c, links=False, ref=None):
    """Return the greeting as a list of lines (no trailing newlines)."""
    width -= 1  # never fill the last column; some terminals wrap early there
    segments = []

    # Last update
    if last is None:
        segments.append(f"{c.yellow}●{c.reset} Last update unknown")
    else:
        text, days = ago(last, ref)
        colour = c.green if days < 7 else c.yellow if days < 14 else c.red
        segments.append(f"{colour}●{c.reset} Updated {colour}{c.bold}{text}{c.reset} "
                        f"{c.dim}({last.astimezone():%a %d %b, %H:%M}){c.reset}")

    # Pending updates
    p = state.get("pending") or {}
    if pending_is_fresh(state, last) and "count" in p:
        count, aur = p["count"], p.get("aur") or 0
        if not count and not aur:
            segments.append(f"{c.green}✓ up to date{c.reset}")
        else:
            details = []
            if p.get("download"):
                details.append(human_size(p["download"]))
            secs = estimate_seconds(state.get("history", []), count, p.get("download") or 0,
                                    includes_download, cfg["download_mb_per_s"])
            if secs:
                details.append(human_duration(secs))
            if aur and count:
                details.append(f"+{aur} AUR")
            label = f"{count} pending" if count else f"{aur} AUR pending"
            extra = f" {c.dim}({', '.join(details)}){c.reset}" if details else ""
            segments.append(f"{c.yellow}{c.bold}▲ {label}{c.reset}{extra}")
    elif p.get("error"):
        segments.append(f"{c.red}✗ update check failed{c.reset}")
    else:
        segments.append(f"{c.dim}… checking for updates{c.reset}")

    # News
    new = news_since(state, last)
    flagged = sum(1 for i in new if i.get("important"))
    if new:
        if flagged:
            segments.append(f"{c.red}{c.bold}⚠ {len(new)} news{c.reset}")
        else:
            segments.append(f"{c.cyan}ℹ {len(new)} news{c.reset}")

    # Quiet health warnings
    news_state = state.get("news") or {}
    if state.get("last_fetch") and hours_since(from_iso(news_state.get("last_fetch_ok"))) > 24:
        segments.append(f"{c.dim}{c.yellow}feeds stale{c.reset}")
    if p.get("lists_age_hours", 0) > 72:
        segments.append(f"{c.dim}{c.yellow}apt lists {p['lists_age_hours'] / 24:.0f}d old{c.reset}")

    lines = wrap_segments(segments, width, c)

    # News lines, flagged first, newest first within each group
    new.sort(key=lambda i: i["date"], reverse=True)
    new.sort(key=lambda i: not i.get("important"))  # stable: keeps newest-first within each group
    shown = new[:cfg["max_news"]]
    if shown:
        src_w = max(len(i["source"]) for i in shown)
        for i in shown:
            mark = f"{c.red}{c.bold}!{c.reset}" if i.get("important") else " "
            date = from_iso(i["date"]).astimezone()
            prefix_len = len(INDENT) + 2 + src_w + 2 + 6 + 2
            title = truncate(i["title"], width - prefix_len)
            title = link(title, i.get("link"), links)
            if i.get("important"):
                title = f"{c.bold}{title}{c.reset}"
            lines.append(f"{INDENT}{mark} {c.cyan}{i['source']:<{src_w}}{c.reset}  "
                         f"{c.dim}{date:%d %b}{c.reset}  {title}")
        if len(new) > len(shown):
            lines.append(f"{INDENT}  {c.dim}… +{len(new) - len(shown)} more · update-watch news{c.reset}")
    return lines


def terminal_width():
    return shutil.get_terminal_size((100, 24)).columns


def status(cfg):
    c = Colour()
    state = load_state()
    backend = get_backend(cfg["family"])
    last = last_upgrade(backend, state)
    for line in render(cfg, state, last, backend.history_includes_download, terminal_width(), c,
                       hyperlinks_enabled(cfg, c)):
        print(line)

    stale = hours_since(from_iso(state.get("last_fetch"))) > cfg["refresh_hours"] or not pending_is_fresh(state, last)
    if stale:
        _spawn_fetch()


def news(cfg):
    """Detailed view: pending update numbers and every news item since the last update, with URLs."""
    c = Colour()
    state = load_state()
    backend = get_backend(cfg["family"])
    last = last_upgrade(backend, state)
    p = state.get("pending") or {}

    print(f"{c.bold}Last update{c.reset}   {last.astimezone():%a %d %b %Y, %H:%M} ({ago(last)[0]})"
          if last else f"{c.bold}Last update{c.reset}   unknown")
    if pending_is_fresh(state, last) and "count" in p:
        print(f"{c.bold}Pending{c.reset}       {p['count']} packages"
              + (f", {p['aur']} AUR" if p.get("aur") else ""))
        if p.get("download") is not None:
            print(f"{c.bold}Download{c.reset}      {human_size(p['download'])}")
        if p.get("install_delta") is not None:
            sign = "+" if p["install_delta"] >= 0 else ""
            print(f"{c.bold}Disk change{c.reset}   {sign}{human_size(p['install_delta'])}")
        secs = estimate_seconds(state.get("history", []), p["count"], p.get("download") or 0,
                                backend.history_includes_download, cfg["download_mb_per_s"])
        if secs:
            print(f"{c.bold}Estimate{c.reset}      {human_duration(secs)} "
                  f"{c.dim}(from your last {min(len(state.get('history', [])), 10)} upgrades){c.reset}")
        print(f"{c.bold}Checked{c.reset}       {from_iso(p['checked']).astimezone():%a %d %b, %H:%M}")
    elif p.get("error"):
        print(f"{c.bold}Pending{c.reset}       check failed: {p['error']}")

    new = news_since(state, last)
    print(f"\n{c.bold}News since your last update ({len(new)}){c.reset}")
    if not new:
        print(f"  {c.dim}Nothing new.{c.reset}")
    for i in new:
        mark = f"{c.red}!{c.reset}" if i.get("important") else " "
        print(f" {mark} {c.cyan}{i['source']}{c.reset} {c.dim}{from_iso(i['date']).astimezone():%d %b %Y}{c.reset}"
              f"  {i['title']}")
        if i.get("link"):
            print(f"     {c.dim}{i['link']}{c.reset}")
    return 0


def demo(cfg):
    """Render the greeting for a few made-up situations so you can judge the look."""
    c = Colour()
    ref = now()
    width = terminal_width()
    links = hyperlinks_enabled(cfg, c)
    cfg = dict(cfg, max_news=cfg.get("max_news", 5))
    history = [(40, 200.0), (25, 140.0), (60, 260.0)]

    def item(source, title, days_ago, important=False):
        return {"source": source, "title": title, "link": "https://example.com/" + title.split()[0].lower(),
                "date": (ref - timedelta(days=days_ago)).isoformat(), "important": important}

    fresh = ref.isoformat()
    scenarios = [
        ("Up to date, nothing new", ref - timedelta(days=1),
         {"pending": {"count": 0, "checked": fresh}, "news": {"items": [], "last_fetch_ok": fresh},
          "last_fetch": fresh}),
        ("Updates waiting + news to read first", ref - timedelta(days=4),
         {"pending": {"count": 194, "download": 522_000_000, "install_delta": 3_000_000, "aur": 2,
                      "checked": fresh},
          "history": history, "last_fetch": fresh,
          "news": {"last_fetch_ok": fresh, "items": [
              item("Arch", "foo >= 2.0 requires manual intervention", 2, True),
              item("CachyOS", "CachyOS October 2026 release", 1)]}}),
        ("Overdue, offline, lots of news", ref - timedelta(days=23),
         {"pending": {"error": "could not refresh package databases (offline?)"},
          "history": history, "last_fetch": fresh,
          "news": {"last_fetch_ok": (ref - timedelta(days=3)).isoformat(), "items": [
              item("Arch", "NVIDIA 590 drops support for Pascal GPUs, manual intervention required", 20, True),
              item("Arch", "grub 2.14 requires re-running grub-install", 15, True),
              item("CachyOS forum", "Kernel 7.2 regression with some Realtek Wi-Fi cards", 9, True),
              item("CachyOS", "CachyOS September 2026 release", 18),
              item("Arch", "New Arch Linux wiki theme", 12),
              item("CachyOS", "Mirror maintenance this weekend", 6),
              item("Arch", "Arch Summit 2026 recordings", 4)]}}),
    ]
    for title, last, state in scenarios:
        print(f"\n{c.dim}── {title} {'─' * max(0, min(width, 90) - len(title) - 4)}{c.reset}")
        for line in render(cfg, state, last, True, width, c, links, ref):
            print(line)
    print()
    return 0
