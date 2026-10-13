"""Detect the distro family from /etc/os-release and return the matching backend."""
import shutil

FAMILIES = ("arch", "debian", "fedora")


def os_release(path="/etc/os-release"):
    info = {}
    try:
        with open(path) as f:
            for line in f:
                key, sep, value = line.strip().partition("=")
                if sep:
                    info[key] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return info


def ids(info):
    return [info.get("ID", "").lower()] + info.get("ID_LIKE", "").lower().split()


def detect_family(info=None):
    info = os_release() if info is None else info
    found = ids(info)
    if any(i in ("arch", "archlinux") for i in found):
        return "arch"
    if any(i in ("debian", "ubuntu") for i in found):
        return "debian"
    if any(i in ("fedora", "rhel", "centos") for i in found):
        return "fedora"
    # Unknown ID: fall back to whichever package manager exists.
    for tool, family in (("pacman", "arch"), ("apt-get", "debian"), ("dnf5", "fedora"), ("dnf", "fedora")):
        if shutil.which(tool):
            return family
    return None


def pretty_name(info=None):
    info = os_release() if info is None else info
    return info.get("PRETTY_NAME") or info.get("NAME") or "Unknown Linux"


def get_backend(family):
    if family == "arch":
        from .backends.arch import ArchBackend
        return ArchBackend()
    if family == "debian":
        from .backends.debian import DebianBackend
        return DebianBackend()
    if family == "fedora":
        from .backends.fedora import FedoraBackend
        return FedoraBackend()
    raise ValueError(f"unsupported distro family: {family!r}")
