"""Per-distro-family backends. Every method works without root.

Interface (see base.Backend):
  last_upgrade(full=False) -> aware datetime of the last system upgrade, or None
  history()                -> [(packages, seconds)] for past upgrades, oldest first
  pending()                -> {"count", "download", "install_delta", ...}; raises PendingError
  missing_tools()          -> [(tool, install hint)] for helpers that aren't installed
"""
