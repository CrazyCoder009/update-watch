# update-watch: show last system update + news after the greeting (fastfetch).
# Runs once, on the first prompt, so it prints after whatever fish_greeting does.
status is-interactive; or return

function __update_watch_once --on-event fish_prompt
    functions -e __update_watch_once
    test -x ~/.local/bin/update-watch-status; and ~/.local/bin/update-watch-status
end
