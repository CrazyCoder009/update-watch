"""Arch family: Arch, CachyOS, EndeavourOS, Manjaro, Garuda...

Last upgrade/history come from /var/log/pacman.log. Pending updates use a private
copy of the sync databases (like `checkupdates`), refreshed with fakeroot.
"""
import os
import re
import shutil
from datetime import datetime

from ..config import CACHE_DIR
from ..util import parse_size, run
from .base import Backend, PendingError

LINE = re.compile(r"^\[([^\]]+)\] \[([A-Z-]+)\] (.*)$")
PRINT_LINE = re.compile(r"^(\S+)/(\S+) (\d+)$")


def _ts(text):
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M"):
        try:
            d = datetime.strptime(text, fmt)
            return d if d.tzinfo else d.astimezone()
        except ValueError:
            pass
    return None


def parse_pacman_log(path):
    """Yield (start, end, packages_upgraded) for each completed `pacman -Syu`."""
    try:
        f = open(path, errors="replace")
    except OSError:
        return
    with f:
        start, count = None, 0
        for line in f:
            m = LINE.match(line)
            if not m:
                continue
            ts, tag, msg = m.groups()
            if tag == "PACMAN":
                if msg.startswith("starting full system upgrade"):
                    start, count = _ts(ts), 0
                elif msg.startswith("Running"):
                    start = None
            elif tag == "ALPM" and start is not None:
                if msg.startswith("upgraded "):
                    count += 1
                elif msg.startswith("transaction completed"):
                    end = _ts(ts)
                    if count and end:
                        yield start, end, count
                    start = None


def _info_sizes(text):
    """Parse `pacman -Si/-Qi` output into {name: installed_bytes}."""
    sizes, name = {}, None
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key = key.strip()
        if key == "Name":
            name = value.strip()
        elif key == "Installed Size" and name:
            sizes[name] = parse_size(value)
    return sizes


def _chunks(items, n=200):
    for i in range(0, len(items), n):
        yield items[i:i + n]


class ArchBackend(Backend):
    name = "arch"
    history_includes_download = True
    required_tools = (("pacman", "pacman"), ("fakeroot", "fakeroot"))

    def __init__(self, log_path=None, db_dir=None):
        self.log_path = log_path or os.environ.get("UPDATE_WATCH_PACMAN_LOG", "/var/log/pacman.log")
        self.db_dir = db_dir or os.path.join(CACHE_DIR, "pacman-db")

    def last_upgrade(self, full=False):
        last = None
        for _, end, _ in parse_pacman_log(self.log_path):
            last = end
        return last

    def history(self):
        return [(n, (end - start).total_seconds()) for start, end, n in parse_pacman_log(self.log_path)]

    def _sync_db(self):
        os.makedirs(self.db_dir, exist_ok=True)
        rc, out = run(["pacman-conf", "DBPath"])
        system_db = (out.strip() if rc == 0 and out.strip() else "/var/lib/pacman/").rstrip("/")
        local = os.path.join(self.db_dir, "local")
        if not os.path.islink(local):
            os.symlink(os.path.join(system_db, "local"), local)
        lock = os.path.join(self.db_dir, "db.lck")
        if os.path.exists(lock):
            os.remove(lock)  # stale lock from an interrupted run; we're the only user of this db
        # Newer pacman sandboxes downloads; flag names changed across versions, so try in order.
        for extra in (["--disable-sandbox-filesystem"], ["--disable-sandbox"], []):
            rc, _ = run(["fakeroot", "--", "pacman", "-Sy", *extra, "--dbpath", self.db_dir,
                         "--logfile", "/dev/null"], timeout=300)
            if rc == 0:
                return
        raise PendingError("could not refresh package databases (offline?)")

    def pending(self):
        if not shutil.which("fakeroot"):
            raise PendingError("needs fakeroot (sudo pacman -S fakeroot)")
        self._sync_db()
        base = ["pacman", "--dbpath", self.db_dir, "--logfile", "/dev/null"]
        rc, out = run(base + ["-Sup", "--noconfirm", "--print-format", "%r/%n %s"])
        targets = []
        download = 0
        if rc == 0:
            for line in out.splitlines():
                m = PRINT_LINE.match(line.strip())
                if m:
                    targets.append(f"{m.group(1)}/{m.group(2)}")
                    download += int(m.group(3))
        else:
            # Dependency problems make -Sup fail; still report a count.
            rc, out = run(base + ["-Qu"])
            names = [l.split()[0] for l in out.splitlines() if l.strip() and "[ignored]" not in l]
            return {"count": len(names), "download": None, "install_delta": None, **self._aur()}

        new_sizes, old_sizes = {}, {}
        for chunk in _chunks(targets):
            new_sizes.update(_info_sizes(run(base + ["-Si"] + chunk)[1]))
            old_sizes.update(_info_sizes(run(["pacman", "-Qi"] + [t.split("/", 1)[1] for t in chunk])[1]))
        delta = sum(size - old_sizes.get(name, 0) for name, size in new_sizes.items())
        return {"count": len(targets), "download": download, "install_delta": delta, **self._aur()}

    def _aur(self):
        for helper in ("paru", "yay"):
            if shutil.which(helper):
                rc, out = run([helper, "-Qua"], timeout=90)
                if rc is not None:
                    return {"aur": len([l for l in out.splitlines() if l.strip()])}
        return {}
