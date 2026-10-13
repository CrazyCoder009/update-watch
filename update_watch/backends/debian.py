"""Debian family: Debian, Ubuntu, Linux Mint, Pop!_OS, elementary...

Last upgrade/history come from /var/log/apt/history.log (+ rotated .gz files).
Pending updates are simulated with `apt-get -s`, using the package lists the
system's apt-daily timer keeps fresh (no root needed).
"""
import glob
import gzip
import os
import re
from datetime import datetime

from ..util import run
from .base import Backend, PendingError

UPGRADE_CMD = re.compile(r"\b(upgrade|full-upgrade|dist-upgrade|unattended-upgrade)\b")
INST = re.compile(r"^Inst (\S+) (?:\[([^\]]*)\] )?\((\S+) .*\[([^\]]+)\]\)")
LISTS_DIR = "/var/lib/apt/lists"


def _date(value):
    try:
        return datetime.strptime(" ".join(value.split()), "%Y-%m-%d %H:%M:%S").astimezone()
    except ValueError:
        return None


def parse_history(text):
    """Yield dicts for each history.log stanza."""
    for block in re.split(r"\n\s*\n", text):
        entry = {}
        for line in block.strip().splitlines():
            key, sep, value = line.partition(": ")
            if sep:
                entry[key.strip()] = value.strip()
        if entry:
            yield entry


def is_upgrade(entry):
    """True for apt upgrade/full-upgrade, unattended-upgrades and GUI updaters (no Commandline)."""
    if "Upgrade" not in entry:
        return False
    cmd = entry.get("Commandline")
    return cmd is None or bool(UPGRADE_CMD.search(cmd))


def _rotation_number(path):
    m = re.search(r"history\.log\.(\d+)", path)
    return int(m.group(1)) if m else 0


def upgrade_count(entry):
    # "pkg:amd64 (1.0, 1.1), other:all (2, 3)" -> 2
    return entry.get("Upgrade", "").count("(")


class DebianBackend(Backend):
    name = "debian"
    history_includes_download = False  # Start-Date is written after downloads finish
    required_tools = (("apt-get", "apt"), ("apt-cache", "apt"), ("dpkg-query", "dpkg"))

    def __init__(self, log_dir=None):
        self.log_dir = log_dir or os.environ.get("UPDATE_WATCH_APT_LOG_DIR", "/var/log/apt")

    def _entries(self, full):
        paths = [os.path.join(self.log_dir, "history.log")]
        if full:
            rotated = glob.glob(os.path.join(self.log_dir, "history.log.*"))
            rotated.sort(key=_rotation_number, reverse=True)  # .3.gz, .2.gz, .1 -> oldest first
            paths = rotated + paths
        entries = []
        for path in paths:
            try:
                opener = gzip.open if path.endswith(".gz") else open
                with opener(path, "rt", errors="replace") as f:
                    entries.extend(parse_history(f.read()))
            except OSError:
                continue
        return [e for e in entries if is_upgrade(e)]

    def last_upgrade(self, full=False):
        last = None
        for e in self._entries(full):
            d = _date(e.get("End-Date") or e.get("Start-Date", ""))
            if d and (last is None or d > last):
                last = d
        return last

    def history(self):
        out = []
        for e in self._entries(full=True):
            start, end = _date(e.get("Start-Date", "")), _date(e.get("End-Date", ""))
            if start and end and upgrade_count(e):
                out.append((upgrade_count(e), (end - start).total_seconds()))
        return out

    def lists_age_hours(self):
        stamps = [os.path.getmtime(p) for p in glob.glob(os.path.join(LISTS_DIR, "*Release"))]
        if not stamps:
            return None
        return (datetime.now().timestamp() - max(stamps)) / 3600

    def pending(self):
        rc, out = run(["apt-get", "-s", "-o", "Debug::NoLocking=1", "dist-upgrade"])
        if rc != 0:
            raise PendingError("apt-get simulation failed")
        targets = []  # (name, new_version, arch)
        for line in out.splitlines():
            m = INST.match(line)
            if m:
                targets.append((m.group(1), m.group(3), m.group(4)))
        result = {"count": len(targets), "download": 0, "install_delta": 0}
        age = self.lists_age_hours()
        if age is not None:
            result["lists_age_hours"] = round(age, 1)
        if not targets:
            return result

        new = {}
        rc, out = run(["apt-cache", "show", "--no-all-versions"] + [f"{n}={v}" for n, v, _ in targets])
        for stanza in parse_history(out):
            key = (stanza.get("Package"), stanza.get("Version"), stanza.get("Architecture"))
            new.setdefault(key, (int(stanza.get("Size", 0) or 0), int(stanza.get("Installed-Size", 0) or 0) * 1024))

        old = {}
        rc, out = run(["dpkg-query", "-W", "-f", "${Package} ${Architecture} ${Installed-Size}\n"]
                      + [n for n, _, _ in targets])
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[2].isdigit():
                old[(parts[0], parts[1])] = int(parts[2]) * 1024

        for name, version, arch in targets:
            size, installed = new.get((name, version, arch), (0, 0))
            result["download"] += size
            result["install_delta"] += installed - old.get((name, arch), 0)
        return result
