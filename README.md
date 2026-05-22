# scdl — SoundCloud & YouTube downloader

Local fork of [scdl-org/scdl](https://github.com/scdl-org/scdl), a SoundCloud downloader that wraps `yt-dlp` and syncs with your local files.
Extended with YouTube audio/video support and bulk playlist sync.

**Requirements:** Python 3, ffmpeg

## Install

```powershell
uv sync --dev
.\.venv\Scripts\Activate.ps1
```

```python

python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pipx install scdl
pipx upgrade scdl
```

---

## Weekly sync commands

```sh
python src/sync_sc_playlists.py --delay 15    # sync all SoundCloud playlists
python src/cleanup_short_tracks.py --delete   # purge any GO+ 30s snips
python src/sync_yt_playlists.py --delay 15    # sync all YouTube audio playlists
```

---

## SoundCloud

```sh
# Sync one playlist (downloads new, marks removed as [unsync]) (make sure to use the "--sync" flag!)
scdl -l https://soundcloud.com/artist/sets/playlist-name --sync

# Sync all playlists listed in src/sc-playlists-list.md
python src/sync_sc_playlists.py
python src/sync_sc_playlists.py --delay 15      # slower, if hitting 403s
python src/sync_sc_playlists.py --max-errors 3  # abort earlier on rate limits

# One-off downloads
scdl -l https://soundcloud.com/artist/track-name           # single track
scdl -l https://soundcloud.com/artist/sets/playlist-name   # full playlist
scdl -l https://soundcloud.com/artist -a                   # all tracks + reposts
scdl -l https://soundcloud.com/artist -f                   # likes
scdl -l https://soundcloud.com/artist -t                   # uploads only
scdl me -f                                                 # your own likes (requires auth)
```

Archives auto-named and stored in `archive_trackers/sc/`.

### scdl options

```text
-l [url]                        URL can be track/playlist/user
-a                              Download all tracks of user (including reposts)
-p                              Download all playlists of a user
-o [offset]                     Start from item N in playlist (starting with 1)
--force-metadata                Re-embed metadata on already-downloaded files
--sync                          Auto-managed archive: downloads new, marks removed as [unsync]


-t                              Download all uploads of a user (no reposts)
-f                              Download all favorites (likes) of a user
-C                              Download all tracks commented on by a user
-s [search_query]               Search and use the first result
-r                              Download all reposts of user
-c                              Continue if a downloaded file already exists
--download-archive [file]       Keep track of track IDs and skip already-downloaded files
--flac                          Convert lossless originals to FLAC
--original-art                  Download full-res artwork instead of 500×500 JPEG
--original-name                 Keep original filename on original-quality downloads
--no-original                   Only download mp3/m4a/opus, skip original files
--only-original                 Only download tracks with an original file available
--opus                          Prefer opus streams over mp3
--onlymp3                       Download only mp3 files
--name-format [format]          Custom filename format (use "-" to pipe to stdout)
--playlist-name-format [format] Custom filename format for playlist tracks
--overwrite                     Overwrite existing files
--strict-playlist               Abort if one track in a playlist fails
--no-playlist                   Skip playlist entries, download only tracks
--add-description               Save track description to a .txt sidecar file
--path [path]                   Custom download directory
--min-size [size]               Skip tracks smaller than size (k/m/g)
--max-size [size]               Skip tracks larger than size (k/m/g)
--no-album-tag                  Prevent shared cover art across tracks from same album
--extract-artist                Set artist tag from title (e.g. "Artist - Title" format)
--yt-dlp-args [argstring]       Forward extra args to yt-dlp
--client-id [id]                Override the SoundCloud client_id
--auth-token [token]            Override the auth token
--debug                         Verbose logging
```

---

## YouTube — Audio (m4a, 256 kbps)

```sh
# Sync one playlist
python src/ytdl.py -l https://www.youtube.com/playlist?list=PLxxx --sync

# Resume from item N (e.g. after an interruption — skips items 1 to N-1)
python src/ytdl.py -l URL --sync -o 123

# Sync all playlists listed in src/yt-playlists.md
python src/sync_yt_playlists.py
python src/sync_yt_playlists.py --delay 15
```

Files land in `playlists/yt/<playlist name>/`. Archives in `archive_trackers/yt/`.

## YouTube — Video (mp4, best quality)

```sh
# Sync one playlist
python src/ytdl.py -l https://www.youtube.com/playlist?list=PLxxx --sync --video

# Sync all playlists listed in src/yt-video-playlists.md
python src/sync_yt_playlists.py --video
python src/sync_yt_playlists.py --video --delay 15
```

Files land in `playlists/yt-video/<playlist name>/`. Archives in `archive_trackers/yt-video/`.

### Archive files (YouTube)

| File | Content |
| --- | --- |
| `<playlist_id>.txt` | sync archive (tracks downloaded + file paths) |
| `<playlist_id>.failed` | tracks that failed (archive_id + URL) |
| `<playlist_id>.errors.log` | raw error output, appended per run |

Removed-from-playlist tracks are renamed with `[unsync]` prefix (same as SoundCloud).

---

## Authentication

### SoundCloud auth

Find your OAuth token: log into SoundCloud → F12 → Storage → Cookies → `oauth_token`.
Format: `2-322xxx-31626xxx1-SJsONuxxxelkKD`

Add to `scdl/scdl.cfg` (or the system config, see below):

```ini
[scdl]
auth_token = 2-322xxx-...
```

Required for GO+ tracks (256 kbps AAC) and original-quality downloads.

Config file locations:

- Windows: `C:\Users\<username>\.config\scdl\scdl.cfg`
- Mac/Linux: `~/.config/scdl/scdl.cfg`
- If `XDG_CONFIG_HOME` is set: `$XDG_CONFIG_HOME/scdl/scdl.cfg`

### YouTube (cookies) (librewolf example)

yt-dlp reads browser cookies for age-restricted or private content. Set in `ytdl.cfg`:

```ini
[ytdl]
cookies_from_browser = firefox:C:\Users\$USER$\AppData\Roaming\librewolf\Profiles\xxxx.default-default
```

**Close LibreWolf (or your browser) before syncing.** Open browsers rotate session cookies
mid-download and invalidate them after ~150 items on large playlists.

Workflow:

1. Open LibreWolf → log into YouTube (refresh session)
2. **Close LibreWolf completely**
3. Run the sync

---

## GO+ / Restricted tracks (SoundCloud)

The duration filter (`duration>30` in `scdl.cfg`) skips 30 s preview snips automatically.
After each run, three files are written to `archive_trackers/sc/`:

| File | Content |
| --- | --- |
| `<playlist>.txt` | sync archive (downloaded tracks + file paths) |
| `<playlist>.failed` | tracks that failed, tagged by reason |
| `<playlist>.premium` | tracks skipped as ≤30 s snips |

Tags in `.failed`:

| Tag | Meaning |
| --- | --- |
| `[GO+]` | Full track behind SoundCloud GO+ paywall (`policy=SNIP`) |
| `[MONETIZE]` | Ad-gated stream yt-dlp cannot negotiate (e.g. major-label uploads) |
| `[BLOCKED]` | Geo/copyright block (`policy=BLOCK`) |
| `[FAIL]` | Any other error, with raw error message appended |

Run `python src/cleanup_short_tracks.py` (dry run) or `--delete` to purge existing snips.

---

## Data layout

```text
playlists/
  sc/                 # SoundCloud audio, one subfolder per playlist
  yt/                 # YouTube audio (m4a), one subfolder per playlist
  yt-video/           # YouTube video (mp4), one subfolder per playlist

archive_trackers/
  sc/                 # per-playlist .txt, .failed, .premium
  yt/                 # per-playlist .txt, .failed, .errors.log
  yt-video/           # per-playlist .txt, .failed, .errors.log

src/
  sc-playlists-list.md      # SoundCloud playlist URLs (gitignored)
  yt-playlists.md           # YouTube audio playlist URLs (gitignored)
  yt-video-playlists.md     # YouTube video playlist URLs (gitignored)

scdl/scdl.cfg         # SC config: client_id, auth_token, path, name_format (gitignored)
ytdl.cfg              # YT config: cookies_from_browser, path, video_path (gitignored)
```

Archive line format: `soundcloud <track_id> <absolute_path>` (SC) or `youtube <video_id> <absolute_path>` (YT).
