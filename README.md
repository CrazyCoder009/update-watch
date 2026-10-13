# update-watch

Shows, in every new terminal (fish, after fastfetch):

- when you last ran a full system upgrade (`pacman -Syu` / `paru` / `yay`), with the date, time and days since
- how many updates are waiting (from `checkupdates`)
- any **Arch News** or **CachyOS** news/announcements posted *since* your last upgrade, with likely breakage/manual-intervention items flagged in red

```
 Last update: Fri 09 Oct 2026, 21:59  (4 days ago)  · 37 pending
 ⚠ 1 news item since your last update (1 flagged) — read before updating:
  ! [Arch] 2026-10-11  foo >= 2.0 requires manual intervention
      https://archlinux.org/news/...
```

Terminal startup never uses the network: a systemd user timer (`update-watch.timer`, every 3h) fetches the feeds into
`~/.cache/update-watch/news.json`, and the greeting only reads that cache plus `/var/log/pacman.log`.

## Install / uninstall

```sh
./install.sh     # symlinks into ~/.local/bin, ~/.config/fish/conf.d, ~/.config/systemd/user; enables timer
./uninstall.sh
```

## Manual use

```sh
update-watch-fetch     # refresh feeds now
update-watch-status    # print the status block
```

## Sources

- Arch News: https://archlinux.org/feeds/news/
- CachyOS blog: https://cachyos.org/rss.xml
- CachyOS forum announcements: https://discuss.cachyos.org/c/announcements/5.rss

Edit `FEEDS` / `IMPORTANT` in `bin/update-watch-fetch` to change sources or the keywords that flag an item.
Note: `informant` (already installed) separately blocks pacman when there is unread Arch News.
