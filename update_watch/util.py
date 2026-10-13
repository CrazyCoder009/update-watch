"""Small helpers shared by every module: subprocess, time, sizes, colours."""
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# Force C locale so tools print parseable numbers/units regardless of user language.
C_ENV = dict(os.environ, LC_ALL="C", LANG="C")


def run(cmd, timeout=120):
    """Run cmd, return (returncode, stdout). Returns (None, '') if it can't be run."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=C_ENV)
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    return p.returncode, p.stdout


ANSI = re.compile(r"\033\[[0-9;]*m|\033\]8;;[^\033]*\033\\")


def visible_len(text):
    """Length on screen, ignoring colour codes and OSC 8 hyperlinks."""
    return len(ANSI.sub("", text))


def now():
    return datetime.now(timezone.utc)


def parse_date(text):
    """Parse RFC 822 (RSS) or ISO 8601 (Atom/RDF) dates into aware datetimes."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        d = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def iso(d):
    return d.isoformat() if d else None


def from_iso(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except (TypeError, ValueError):
        return None


UNITS = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4,
         "kB": 1000, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3,
         "k": 1024, "M": 1024 ** 2, "G": 1024 ** 3}


def parse_size(text):
    """'9.05 MiB' -> bytes."""
    parts = text.replace(",", ".").split()
    if not parts:
        return 0
    try:
        value = float(parts[0])
    except ValueError:
        return 0
    return int(value * UNITS.get(parts[1] if len(parts) > 1 else "B", 1))


def human_size(n):
    sign = "-" if n < 0 else ""
    n = abs(n)
    for unit, div in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if n >= div:
            v = n / div
            return f"{sign}{v:.1f} {unit}" if v < 10 else f"{sign}{v:.0f} {unit}"
    return f"{sign}{n} B"


def human_duration(seconds):
    if seconds < 60:
        return "<1 min"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"~{minutes} min"
    h, m = divmod(minutes, 60)
    return f"~{h} h {m} min" if m else f"~{h} h"


def ago(d, ref=None):
    """('4 days ago', 4) based on local calendar dates."""
    ref = (ref or now()).astimezone()
    days = (ref.date() - d.astimezone().date()).days
    if days <= 0:
        return "today", 0
    return ("1 day ago" if days == 1 else f"{days} days ago"), days


def hours_since(d):
    return (now() - d).total_seconds() / 3600 if d else float("inf")


class Colour:
    def __init__(self, enabled=None):
        if enabled is None:
            enabled = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        codes = {"reset": 0, "bold": 1, "dim": 2, "red": 31, "green": 32, "yellow": 33, "cyan": 36}
        for name, code in codes.items():
            setattr(self, name, f"\033[{code}m" if enabled else "")
