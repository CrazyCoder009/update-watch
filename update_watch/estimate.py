"""Rough install-time estimate learned from this machine's past upgrades."""

FALLBACK_SECONDS_PER_PACKAGE = 2.0
MAX_SAMPLE_SECONDS = 4 * 3600  # ignore upgrades left waiting at a prompt for hours
SAMPLES = 10


def median(values):
    # statistics.median pulls in decimal/fractions; this runs on every shell start.
    v = sorted(values)
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2


def seconds_per_package(history):
    rates = [secs / n for n, secs in history if n > 0 and 0 < secs < MAX_SAMPLE_SECONDS]
    rates = rates[-SAMPLES:]
    return median(rates) if rates else None


def estimate_seconds(history, count, download_bytes, includes_download, mb_per_s):
    """Seconds to download + install `count` packages.

    history: [(packages, seconds)] oldest first. If those durations already
    include download time (pacman), only add download time when there is no history.
    """
    if not count:
        return 0
    rate = seconds_per_package(history)
    total = (rate or FALLBACK_SECONDS_PER_PACKAGE) * count
    if download_bytes and (rate is None or not includes_download):
        total += download_bytes / (max(mb_per_s, 0.1) * 1e6)
    return total
