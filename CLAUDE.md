# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a local fork/customization of [scdl-org/scdl](https://github.com/scdl-org/scdl), a SoundCloud downloader that wraps `yt-dlp`. The upstream README describes the package well. The local additions are:

- `src/sync_sc_playlists.py` — a standalone bulk-sync script for managing many playlists at once
- `scdl/patches/sync_download_archive.py` — custom sync archive management (not in upstream)
- `scdl/scdl.cfg` — local config (gitignored credentials, local paths)

## Commands

```powershell
# Install / activate environment
uv sync --dev
.\.venv\Scripts\Activate.ps1

# Lint
ruff check scdl/
ruff format scdl/

# Type check
mypy

# Tests
pytest

# Run the downloader (single playlist)
scdl -l <url> --sync

# Sync all playlists from the list file
python src/sync_sc_playlists.py
python src/sync_sc_playlists.py --delay 5 --max-errors 3
```

## Architecture

### `scdl/scdl.py`
The main entry point. `_main()` parses CLI args (docopt), loads `scdl.cfg`, then calls `download_url()`. `_build_ytdl_params()` translates scdl's CLI flags into yt-dlp API params. The output filename template is built by `_build_ytdl_output_filename()` and switched per-track at runtime by `OuttmplPP`.

### `scdl/patches/`
Custom yt-dlp post/pre-processors injected into the `YoutubeDL` instance in `download_url()`:
- `sync_download_archive.py` — `SyncDownloadHelper` manages the `--sync` archive file. It hooks into `_match_entry` to track which IDs are seen, then in `post_download()` renames removed tracks to `[unsync] <name>` and rewrites the archive. It also detects playlist renames and moves files accordingly.
- `mutagen_postprocessor.py` — replaces yt-dlp's built-in EmbedThumbnail/FFmpegMetadata with a mutagen-based one for better format support.
- `switch_outtmpl_preprocessor.py` (`OuttmplPP`) — switches the output template between a standalone-track format and a playlist-track format based on `info_dict["playlist"]`.
- `original_filename_preprocessor.py` — uses the SC original filename for original-quality downloads.
- `thumbnail_selection.py` — filters thumbnails to `t500x500`.
- `trim_filenames.py` — trims filenames to 240 bytes.
- `old_archive_ids.py` — backward compat shim for pre-v3 archive IDs.

### `src/sync_sc_playlists.py`

Reads playlist URLs from `src/sc-playlists-list.md` (one `https://...` URL per line), then for each URL:
1. `heal_all_archives()` — fixes stale archive paths (missing `sc/` layer, digit-padding mismatches) without network access.
2. `fix_index_shifts()` — runs `yt-dlp --flat-playlist` to fetch current track order from SC, compares to the archive, and renames local files so they match the new indices before scdl runs. This avoids re-downloads when tracks are deleted from a playlist, shifting the indices of remaining tracks.
3. `run_scdl()` — runs `scdl --sync` as a subprocess, monitors output for consecutive errors (rate-limit guard), and aborts early if needed.

### Data Layout
```
archive_trackers/sc/        # per-playlist archive .txt files (format: "soundcloud <id> <filepath>")
playlists/sc/               # downloaded audio files, one subfolder per playlist
src/sc-playlists-list.md            # list of SC playlist URLs to sync (gitignored)
scdl/scdl.cfg               # local config (client_id, auth_token, path, name_format)
```

### Archive File Format
Each line: `soundcloud <track_id> <absolute_path_to_file>`

The archive is the source of truth for `--sync`. `SyncDownloadHelper` reads it on startup and rewrites it after every run.

## Config

`scdl/scdl.cfg` (gitignored for credentials):
```ini
[scdl]
client_id =
auth_token =
path = playlists/sc
name_format = [%(id)s] %(uploader)s - %(title)s.%(ext)s
playlist_name_format = %(playlist_index)03d. %(uploader)s - %(title)s.%(ext)s
yt_dlp_args = --match-filters duration>30
```

The `yt_dlp_args` filter (`duration>30`) skips GO+ preview tracks (≤30s).
