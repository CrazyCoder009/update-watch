"""Fedora family: Fedora, Nobara, Ultramarine, RHEL/Alma/Rocky...

Last upgrade/history come from the dnf history databases (dnf5 and dnf4 — GNOME
Software/PackageKit still record into the dnf4 one). Pending updates use
`dnf repoquery --upgrades` against the system metadata cache that
dnf-makecache.timer keeps fresh.
"""
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone

from ..util import run
from .base import Backend, PendingError

HISTORY_DBS = (
    "/usr/lib/sysimage/libdnf5/transaction_history.sqlite",  # dnf5 (Fedora 41+)
    "/var/lib/dnf/history.sqlite",                           # dnf4 / PackageKit
)
UPGRADE_CMD = re.compile(r"\b(upgrade|update|distro-sync|dup|offline|system-upgrade)\b", re.I)
DNF4_ACTION_UPGRADE = 6


def read_history_db(path):
    """Return [(begin, end, cmdline, upgraded_count)] from a dnf4 or dnf5 history db."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        trans_cols = {r[1] for r in con.execute("PRAGMA table_info(trans)")}
        item_cols = {r[1] for r in con.execute("PRAGMA table_info(trans_item)")}
        cmd_col = "description" if "description" in trans_cols else "cmdline"
        if "action_id" in item_cols:  # dnf5: actions are a lookup table
            action_col = "action_id"
            ids = [r[0] for r in con.execute("SELECT id FROM trans_item_action WHERE name = 'Upgrade'")]
        else:
            action_col = "action"
            ids = [DNF4_ACTION_UPGRADE]
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        rows = con.execute(
            f"SELECT t.dt_begin, t.dt_end, t.{cmd_col}, COUNT(ti.id) FROM trans t "
            f"JOIN trans_item ti ON ti.trans_id = t.id WHERE ti.{action_col} IN ({marks}) "
            f"GROUP BY t.id ORDER BY t.dt_begin", ids).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    out = []
    for begin, end, cmd, count in rows:
        if not begin:
            continue
        b = datetime.fromtimestamp(begin, timezone.utc)
        e = datetime.fromtimestamp(end, timezone.utc) if end else b
        out.append((b, e, cmd or "", count))
    return out


def is_system_upgrade(cmd, count):
    # `dnf install foo` can upgrade a dependency or two; GUI updaters leave no useful cmdline.
    return bool(UPGRADE_CMD.search(cmd)) or count >= 5


class FedoraBackend(Backend):
    name = "fedora"
    history_includes_download = False  # dt_begin is after packages are downloaded
    required_tools = (("rpm", "rpm"),)

    def __init__(self, db_paths=None):
        self.db_paths = db_paths or HISTORY_DBS

    def _upgrades(self):
        rows = []
        for path in self.db_paths:
            if os.path.exists(path):
                rows.extend(r for r in read_history_db(path) if is_system_upgrade(r[2], r[3]))
        rows.sort(key=lambda r: r[0])
        return rows

    def last_upgrade(self, full=False):
        rows = self._upgrades()
        return rows[-1][1] if rows else None

    def history(self):
        return [(count, (end - begin).total_seconds()) for begin, end, _, count in self._upgrades()]

    def missing_tools(self):
        missing = super().missing_tools()
        if not (shutil.which("dnf5") or shutil.which("dnf")):
            missing.append(("dnf", "dnf"))
        return missing

    def pending(self):
        dnf = shutil.which("dnf5") or shutil.which("dnf")
        if not dnf:
            raise PendingError("dnf not found")
        system_cache = "/var/cache/libdnf5" if dnf.endswith("dnf5") or os.path.isdir("/var/cache/libdnf5") \
            else "/var/cache/dnf"
        query = ["repoquery", "--upgrades", "--latest-limit=1", "-q",
                 "--qf", "%{name}|%{arch}|%{downloadsize}|%{installsize}\\n"]
        # Prefer the system cache (no download as this user); fall back to fetching metadata.
        out = None
        for opts in (["-C", f"--setopt=cachedir={system_cache}"], ["-C"], []):
            rc, text = run([dnf, *opts, *query], timeout=600)
            if rc == 0:
                out = text
                break
        if out is None:
            raise PendingError("dnf repoquery failed")

        targets = {}
        for line in re.split(r"\n|\\n", out):
            parts = line.strip().split("|")
            if len(parts) == 4 and parts[2].isdigit() and parts[3].isdigit():
                targets[(parts[0], parts[1])] = (int(parts[2]), int(parts[3]))
        result = {"count": len(targets), "download": 0, "install_delta": 0}
        if not targets:
            return result

        old = {}
        rc, text = run(["rpm", "-q", "--qf", "%{NAME}|%{ARCH}|%{SIZE}\n"] + sorted({n for n, _ in targets}))
        for line in text.splitlines():
            parts = line.split("|")
            if len(parts) == 3 and parts[2].isdigit():
                key = (parts[0], parts[1])
                old[key] = max(old.get(key, 0), int(parts[2]))
        for key, (download, installed) in targets.items():
            result["download"] += download
            result["install_delta"] += installed - old.get(key, 0)
        return result
