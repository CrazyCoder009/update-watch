"""Paths, user config and cached state (all per-user, no root)."""
import json
import os

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "update-watch")
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache"), "update-watch")
DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share"), "update-watch")
BIN = os.path.join(HOME, ".local", "bin", "update-watch")

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
STATE_FILE = os.path.join(CACHE_DIR, "state.json")
LOCK_FILE = os.path.join(CACHE_DIR, "fetch.lock")

DEFAULTS = {
    "family": None,           # arch | debian | fedora (auto-detected if None)
    "feeds": [],              # [{"name", "url", "flag_all"}]
    "shells": [],
    "scheduler": "none",      # systemd | none
    "download_mb_per_s": 10,  # used for the time estimate where logs don't include downloads
    "refresh_hours": 3,
    "max_news": 6,
    "keep_news_days": 45,
}


def _read_json(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def load_config():
    cfg = dict(DEFAULTS)
    cfg.update(_read_json(CONFIG_FILE))
    return cfg


def config_exists():
    return os.path.exists(CONFIG_FILE)


def save_config(cfg):
    write_json(CONFIG_FILE, cfg)


def load_state():
    return _read_json(STATE_FILE)


def save_state(state):
    write_json(STATE_FILE, state)
