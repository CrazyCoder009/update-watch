import shutil


class PendingError(Exception):
    """Could not determine pending updates (message is shown to the user)."""


class Backend:
    name = ""
    # Whether history() durations already include download time (pacman's log does).
    history_includes_download = False
    # (tool, install hint) pairs that pending() needs.
    required_tools = ()

    def last_upgrade(self, full=False):
        raise NotImplementedError

    def history(self):
        raise NotImplementedError

    def pending(self):
        raise NotImplementedError

    def missing_tools(self):
        return [(tool, hint) for tool, hint in self.required_tools if not shutil.which(tool)]
