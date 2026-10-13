"""Hook `update-watch status` into bash, zsh and fish start-up."""
import os
import pwd
import re
import shutil

from .config import HOME

SHELLS = ("bash", "zsh", "fish")
BEGIN, END = "# >>> update-watch >>>", "# <<< update-watch <<<"
BLOCK_RE = re.compile(r"\n?" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)

BASH_BLOCK = f"""{BEGIN}
if [[ $- == *i* ]] && [ -x "$HOME/.local/bin/update-watch" ]; then "$HOME/.local/bin/update-watch" status; fi
{END}
"""

# Run on the first prompt so it prints after instant-prompt themes (powerlevel10k) set up.
ZSH_BLOCK = f"""{BEGIN}
if [[ -o interactive && -x "$HOME/.local/bin/update-watch" ]]; then
  _update_watch_once() {{ precmd_functions=(${{precmd_functions:#_update_watch_once}}); "$HOME/.local/bin/update-watch" status; }}
  precmd_functions+=(_update_watch_once)
fi
{END}
"""

# conf.d runs before config.fish, so wait for the first prompt to print after fish_greeting.
FISH_SNIPPET = """# Added by update-watch (remove with: update-watch uninstall)
status is-interactive; or return

function __update_watch_once --on-event fish_prompt
    functions -e __update_watch_once
    test -x ~/.local/bin/update-watch; and ~/.local/bin/update-watch status
end
"""


def rc_path(shell):
    if shell == "bash":
        return os.path.join(HOME, ".bashrc")
    if shell == "zsh":
        return os.path.join(os.environ.get("ZDOTDIR") or HOME, ".zshrc")
    config = os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")
    return os.path.join(config, "fish", "conf.d", "update-watch.fish")


def login_shell():
    try:
        return os.path.basename(pwd.getpwuid(os.getuid()).pw_shell)
    except KeyError:
        return os.path.basename(os.environ.get("SHELL", ""))


def available():
    return [s for s in SHELLS if shutil.which(s)]


def is_installed(shell):
    path = rc_path(shell)
    if shell == "fish":
        return os.path.exists(path)
    try:
        with open(path) as f:
            return BEGIN in f.read()
    except OSError:
        return False


def install(shell):
    path = rc_path(shell)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if shell == "fish":
        if os.path.islink(path):  # v1 symlinked this into the repo
            os.remove(path)
        with open(path, "w") as f:
            f.write(FISH_SNIPPET)
        return path
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    text = BLOCK_RE.sub("\n", text).rstrip("\n")
    block = BASH_BLOCK if shell == "bash" else ZSH_BLOCK
    with open(path, "w") as f:
        f.write((text + "\n\n" if text else "") + block)
    return path


def uninstall(shell):
    path = rc_path(shell)
    if shell == "fish":
        if os.path.lexists(path):
            os.remove(path)
        return
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return
    if BEGIN in text:
        with open(path, "w") as f:
            f.write(BLOCK_RE.sub("\n", text).rstrip("\n") + "\n")
