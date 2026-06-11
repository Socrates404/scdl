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
python src/sync_sc_playlists.py --delay 15 --max-errors 3
python src/sync_sc_playlists.py --force-all        # full sync, detects removals
python src/sync_sc_playlists.py --only 2 5         # run only playlists 2 and 5
python src/sync_sc_playlists.py --skip 3           # skip playlist 3
python src/sync_sc_playlists.py --from 4           # start from playlist 4
python src/sync_sc_playlists.py --resume           # resume last interrupted run
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

Reads playlist URLs from `src/sc-playlists-list.md` (one `https://...` URL per line). **Indices follow line order in that file** — line 1 = `--only 1`, line 15 = `--only 15`. No sorting is applied; the user controls order via the file.

For each URL, unless `--force-all` is passed:

1. **Fast-path** (`_fast_path()`): uses yt-dlp's Python API (no subprocess) to fetch track IDs. First checks the 3 oldest tracks (positions 1–3) as a playlist identity sanity check, then checks position N+1 (where N = archive count) to see if anything new exists. If nothing at N+1 → skip entirely. If something found → run scdl with `-o N+1`.

2. **`run_scdl()`**: runs `scdl --sync --hide-progress` as a subprocess. Filters output to show only new downloads, errors, and warnings. The consecutive-error counter resets on any `[soundcloud]` processing line (not just active download progress), so scattered errors don't falsely trigger the rate-limit abort.

3. **After each playlist**: saves resume state to `.sync-state.json`. Use `--resume` to pick up where a run was interrupted.

`--force-all` disables the fast-path and runs a full scdl sync for every playlist — the only mode that detects removed tracks (`[unsync]`).

### Data Layout

```text
archive_trackers/sc/        # per-playlist archive .txt files (format: "soundcloud <id> <filepath>")
playlists/sc/               # downloaded audio files, one subfolder per playlist
src/sc-playlists-list.md    # list of SC playlist URLs to sync (gitignored)
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
