"""Distro news feeds: catalog, per-distro defaults, fetching and flagging."""
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timedelta
from html import unescape

from .distro import ids
from .util import from_iso, iso, now, parse_date

TIMEOUT = 20

CATALOG = {
    "arch":            {"name": "Arch", "url": "https://archlinux.org/feeds/news/"},
    "cachyos":         {"name": "CachyOS", "url": "https://cachyos.org/rss.xml"},
    "cachyos-forum":   {"name": "CachyOS forum", "url": "https://discuss.cachyos.org/c/announcements/5.rss"},
    "endeavouros":     {"name": "EndeavourOS", "url": "https://endeavouros.com/feed/"},
    "manjaro":         {"name": "Manjaro", "url": "https://forum.manjaro.org/c/announcements/stable-updates/12.rss"},
    "debian":          {"name": "Debian", "url": "https://www.debian.org/News/news"},
    "ubuntu":          {"name": "Ubuntu", "url": "https://discourse.ubuntu.com/c/announcements/12.rss"},
    "mint":            {"name": "Mint", "url": "https://blog.linuxmint.com/?feed=rss2"},
    "fedora":          {"name": "Fedora", "url": "https://discussion.fedoraproject.org/c/news/announce-list/76.rss"},
    # Every post here is a known problem, so flag them all.
    "fedora-issues":   {"name": "Fedora issues", "url": "https://discussion.fedoraproject.org/c/news/common-issues/82.rss",
                        "flag_all": True},
}

# Distro ID (or ID_LIKE) -> catalog keys enabled by default. First match wins.
DEFAULTS = [
    ("cachyos", ["arch", "cachyos", "cachyos-forum"]),
    ("endeavouros", ["arch", "endeavouros"]),
    ("manjaro", ["manjaro", "arch"]),
    ("arch", ["arch"]),
    ("linuxmint", ["mint", "ubuntu"]),
    ("ubuntu", ["ubuntu"]),
    ("debian", ["debian"]),
    ("fedora", ["fedora", "fedora-issues"]),
]

# Titles matching these are flagged as "read before updating".
IMPORTANT = re.compile(
    r"manual intervention|intervention|requires|breaking|broken|\bbreak|boot|grub|systemd-boot|limine|"
    r"nvidia|mkinitcpio|dracut|initramfs|deprecat|replace|compromis|malicious|incident|regression|"
    r"rollback|data loss|warning|important|action required|known issue|fails?\b|failure|crash",
    re.IGNORECASE,
)


def default_feeds(os_info):
    found = ids(os_info)
    for distro_id, keys in DEFAULTS:
        if distro_id in found:
            return [dict(CATALOG[k], key=k) for k in keys]
    return []


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _child(el, *names):
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def parse_feed(data, source, flag_all=False):
    """Parse RSS 2.0, RSS 1.0 (RDF) or Atom into item dicts."""
    root = ET.fromstring(data)
    items = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title_el = _child(el, "title")
        title = unescape((title_el.text or "").strip()) if title_el is not None else ""
        link_el = _child(el, "link")
        link = ""
        if link_el is not None:
            link = (link_el.text or link_el.get("href") or "").strip()
        date_el = _child(el, "pubDate", "date", "published", "updated")
        date = parse_date(date_el.text if date_el is not None else "")
        if not title or not date:
            continue
        items.append({
            "source": source,
            "title": " ".join(title.split()),
            "link": link,
            "date": iso(date),
            "important": flag_all or bool(IMPORTANT.search(title)),
        })
    return items


def fetch_feed(feed):
    req = urllib.request.Request(feed["url"], headers={"User-Agent": "update-watch (+https://github.com)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return parse_feed(resp.read(), feed["name"], feed.get("flag_all", False))


def refresh(feeds, old_items, keep_days):
    """Fetch every feed; on failure keep that feed's previously cached items."""
    errors, items = [], {}
    for feed in feeds:
        try:
            fetched = fetch_feed(feed)
        except Exception as e:  # network, HTTP, XML
            errors.append(f"{feed['name']}: {e}")
            fetched = [i for i in old_items if i.get("source") == feed["name"]]
        for item in fetched:
            items[(item["source"], item["link"] or item["title"])] = item
    cutoff = now() - timedelta(days=keep_days)
    kept = [i for i in items.values() if (from_iso(i["date"]) or cutoff) >= cutoff]
    kept.sort(key=lambda i: i["date"], reverse=True)
    return kept, errors
