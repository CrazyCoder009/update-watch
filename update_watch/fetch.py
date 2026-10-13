"""`update-watch fetch`: refresh news + pending updates into the state cache.

Run by the systemd user timer, or in the background by `status` when the cache is stale.
"""
import os
import sys

from . import news
from .backends.base import PendingError
from .config import CACHE_DIR, LOCK_FILE, load_state, save_state
from .distro import get_backend
from .util import iso, now


def fetch(cfg, quiet=False):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    try:
        return _fetch(cfg, quiet)
    finally:
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass


def _fetch(cfg, quiet):
    state = load_state()
    backend = get_backend(cfg["family"])
    ts = iso(now())

    items, errors = news.refresh(cfg["feeds"], state.get("news", {}).get("items", []), cfg["keep_news_days"])
    state["news"] = {"items": items, "errors": errors, "last_fetch": ts,
                     "last_fetch_ok": ts if not errors else state.get("news", {}).get("last_fetch_ok")}

    try:
        pending = backend.pending()
        pending["checked"] = ts
        state["pending"] = pending
    except PendingError as e:
        state["pending"] = dict(state.get("pending", {}), error=str(e), error_at=ts)

    state["last_upgrade_full"] = iso(backend.last_upgrade(full=True))
    state["history"] = backend.history()[-20:]
    state["last_fetch"] = ts
    save_state(state)

    if not quiet:
        for e in errors:
            print(f"update-watch: feed failed: {e}", file=sys.stderr)
        p = state["pending"]
        if "error" in p and p.get("error_at") == ts:
            print(f"update-watch: update check failed: {p['error']}", file=sys.stderr)
        print(f"update-watch: {len(items)} news items, {p.get('count', '?')} pending updates")
    return 0
