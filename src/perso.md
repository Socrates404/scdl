# Commands

```python

python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pipx install scdl
pipx upgrade scdl

```

# Commands to run weekly
```
python src/sync_sc_playlists.py --delay 15
python src/cleanup_short_tracks.py --delete
python src/sync_yt_playlists.py --delay 15
```

---

## YouTube syncer (ytdl.py)

Downloads YouTube playlists as 256kbps m4a with embedded metadata/thumbnail.
Files land in `playlists\yt\<playlist name>\`. SoundCloud files land in `playlists\sc\`.
Archives and trackers are in `archive_trackers/`.

### Download one playlist

```
python src/ytdl.py -l https://www.youtube.com/playlist?list=PLxxxxx --sync
```

### Sync all YouTube playlists at once

```
python src/sync_yt_playlists.py             # 8s jittered delay between playlists
python src/sync_yt_playlists.py --delay 15  # slower, if hitting 429s
```

Playlist URLs go in `yt-playlists.md` (one per line).

### Authentication — close LibreWolf before syncing

yt-dlp reads LibreWolf cookies **once at startup**. If LibreWolf is open and browsing,
YouTube rotates the session cookies mid-download and invalidates them (~item 150+ on large playlists).

**Workflow:**

1. Open LibreWolf → log into YouTube (refresh session)
2. **Close LibreWolf completely**
3. Run the sync

### Resume from a specific item (-o)

If a sync was interrupted mid-playlist and you know the first 122 items are already done,
skip straight to item 123 — no archive re-check, pure skip:

```sh
python src/ytdl.py -l URL --sync -o 123
```

### Archive files in archive_trackers/

| File | Content |
| --- | --- |
| `<playlist_id>.txt` | sync archive (tracks already downloaded + file paths) |
| `<playlist_id>.failed` | tracks that failed (archive_id + URL, one per line) |
| `<playlist_id>.errors.log` | raw error output per run |

Removed-from-playlist tracks are renamed with `[unsync]` prefix (same as scdl).



## GO+ / restricted tracks

SoundCloud restricts some tracks at the API level — even a valid GO+ auth token cannot bypass this.
Three categories are tracked automatically per playlist in `archive_trackers/`:

| File | What's in it |
| --- | --- |
| `<playlist>.txt` | sync archive (tracks already downloaded) |
| `<playlist>.failed` | tracks that could not be downloaded, tagged by reason |
| `<playlist>.premium` | tracks skipped because they came back as a ≤30 s snip |

**Tags in `.failed`:**

- `[GO+]` — SoundCloud GO+ subscription required (`policy=SNIP`) — full track behind paywall
- `[MONETIZE]` — ad-gated stream yt-dlp cannot negotiate (e.g. Take Five, major-label monetized uploads)
- `[BLOCKED]` — geo/copyright block (`policy=BLOCK`)
- `[FAIL]` — any other download error, with the raw error appended

The duration filter (`duration>30`) in `scdl.cfg` prevents 30 s preview snips from being saved.
Run `python cleanup_short_tracks.py` (dry run) or `python cleanup_short_tracks.py --delete` to purge any existing snips.


# Download one playlist (avoid using it without the "--sync" flag!)
scdl -l https://soundcloud.com/pandadub/sets/the-lost-ship


# Sync playlist: Download only new tracks from a playlist
scdl -l https://soundcloud.com/pandadub/sets/the-lost-ship --sync
(we removed archive.txt argument to auto name the file and place it in archive_trackers)
/!\ it will remove songs that are no longer in the playlist !

# Sync all playlists at once (may fail because of rate limit, individual playlist sync is suggested)

python src/sync_sc_playlists.py             # 8s jittered delay between playlists (safe default)
python src/sync_sc_playlists.py --delay 15  # slower, if still hitting 403s
python src/sync_sc_playlists.py --delay 0   # no delay (risky, may 403)



## Options:
```
-l [url]                        URL can be track/playlist/user
-a                              Download all tracks of user (including reposts)
-t                              Download all uploads of a user (no reposts)
-p                              Download all playlists of a user
--force-metadata                This will set metadata on already downloaded track
-o [offset]                     Start downloading a playlist from the [offset]th track (starting with 1)


### Authentication

* Find your OAuth token by visiting SoundCloud after logging in and opening developer console (press F12) and going to the Storage tab. Then under cookies > soundcloud.com you can find the entry called oauth_token
    auth token format: 2-322xxx-31626xxx1-SJsONuxxxelkKD
* Place OAuth token in the config file (see below)
* You need to have this set to be able to use the `me` option
* You need to have this set to download original files (which may be lossless) if they are available
* If you have a GO+ account it will allow you to download some songs in 256 kbps AAC quality, and songs which are only available with GO+


### Config file locations
* Windows: `C:\Users\username\.config\scdl\scdl.cfg`
* Mac/Linux: `~/.config/scdl/scdl.cfg`
* If `XDG_CONFIG_HOME` is set: `$XDG_CONFIG_HOME/scdl/scdl.cfg`

#### Your `scdl.cfg` should look at least like this:
```scdl.cfg
[DEFAULT]
oauth_token=XXXXXXXXXXX
```