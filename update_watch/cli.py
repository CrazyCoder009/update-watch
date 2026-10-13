import sys

from . import __version__
from .config import config_exists, load_config


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv in ([], ["status"]):  # hot path on every shell start: skip argparse
        return _status()
    import argparse
    parser = argparse.ArgumentParser(
        prog="update-watch",
        description="Last-update reminder, pending update size/time and distro news for your terminal.")
    parser.add_argument("--version", action="version", version=f"update-watch {__version__}")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status", help="print the summary (default; runs on terminal start)")
    f = sub.add_parser("fetch", help="refresh news and pending updates now")
    f.add_argument("--quiet", action="store_true")
    s = sub.add_parser("setup", help="interactive setup (re-run to change settings)")
    s.add_argument("-y", "--yes", action="store_true", help="accept defaults, no questions")
    u = sub.add_parser("uninstall", help="remove hooks, timer, config and cache")
    u.add_argument("-y", "--yes", action="store_true")
    sub.add_parser("doctor", help="show detected distro, config and recent errors")
    args = parser.parse_args(argv)
    cmd = args.cmd or "status"

    if cmd in ("setup", "uninstall", "doctor"):
        from . import installer
        if cmd == "setup":
            return installer.setup(args.yes)
        if cmd == "uninstall":
            return installer.uninstall(args.yes)
        return installer.doctor()

    if not config_exists():
        print("update-watch is not set up yet — run: update-watch setup", file=sys.stderr)
        return 1
    cfg = load_config()
    if cmd == "fetch":
        from .fetch import fetch
        return fetch(cfg, args.quiet)
    return _status()


def _status():
    if not config_exists():
        print("update-watch is not set up yet — run: update-watch setup", file=sys.stderr)
        return 1
    try:
        from .status import status
        status(load_config())
    except Exception as e:  # never break shell start-up
        print(f" update-watch: {e}", file=sys.stderr)
    return 0
