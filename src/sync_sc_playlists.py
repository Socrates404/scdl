#!/usr/bin/env python3
import argparse
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from tqdm import tqdm

_ROOT = Path(__file__).parent.parent
PLAYLIST_FILE = Path(__file__).parent / "sc-playlists-list.md"
ARCHIVE_DIR = _ROOT / "archive_trackers" / "sc"
SC_PLAYLIST_DIR = _ROOT / "playlists" / "sc"
STATE_FILE = _ROOT / ".sync-state.json"
RATE_LIMIT_COOLDOWN = 120
_SANITY_N = 3   # first N tracks fetched to verify playlist identity

_verbose = False


def parse_args():
    p = argparse.ArgumentParser(description="Sync all SoundCloud playlists in sc-playlists-list.md")
    p.add_argument("--delay", type=float, default=8.0, metavar="S",
        help="Base inter-playlist delay in seconds (default 8, actual ±50%% jitter)")
    p.add_argument("--max-errors", type=int, default=5, metavar="N",
        help="Abort a playlist after N consecutive track errors (default 5)")
    p.add_argument("--force-all", action="store_true",
        help="Disable fast-path: full sync every playlist (also detects removed tracks)")
    p.add_argument("--resume", action="store_true",
        help="Resume the last interrupted run from where it left off")
    p.add_argument("--from", dest="from_index", type=int, metavar="N",
        help="Skip playlists 1..(N-1) and start at index N (1-based)")
    p.add_argument("--only", type=int, nargs="+", metavar="N",
        help="Run only these playlist numbers (1-based, space-separated)")
    p.add_argument("--skip", type=int, nargs="+", metavar="N",
        help="Skip these playlist numbers (1-based, space-separated)")
    p.add_argument("--verbose", action="store_true",
        help="Show all scdl/yt-dlp output without filtering")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Archive / URL helpers
# ---------------------------------------------------------------------------

def archive_path(url: str) -> Path:
    url_path = urlparse(url).path.strip("/")
    parts = [p for p in url_path.split("/") if p != "sets"]
    return ARCHIVE_DIR / f"{'_'.join(parts) if parts else 'unknown'}.txt"


def is_empty(path: Path) -> bool:
    return not path.exists() or path.stat().st_size == 0


def _label(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path.replace("/sets/", " / ").replace("/", " / ")


# ---------------------------------------------------------------------------
# Resume state
# ---------------------------------------------------------------------------

def _save_state(urls: list[str], completed: int) -> None:
    STATE_FILE.write_text(json.dumps({"urls": urls, "completed": completed}), encoding="utf-8")


def _load_state() -> dict | None:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else None
    except Exception:
        return None


def _clear_state() -> None:
    STATE_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Smart scan (fast-path)
# ---------------------------------------------------------------------------

def _archive_ids(url: str) -> set[str]:
    p = archive_path(url)
    if not p.exists():
        return set()
    ids: set[str] = set()
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            ids.add(parts[1])
    return ids


def _fetch_ids_at(url: str, items: str) -> list[str] | None:
    """
    Fetch track IDs for the given playlist-items range via yt-dlp Python API.
    Returns a list (possibly empty if range is past end) or None on error.

    Uses the API directly instead of a subprocess to avoid Windows console
    output bypass (WriteConsoleW leaks through capture_output=True on Windows).
    """
    try:
        from yt_dlp import YoutubeDL
        ids: list[str] = []
        params = {
            "extract_flat": True,
            "playlist_items": items,
            "quiet": True,
            "no_warnings": True,
            "allowed_extractors": ["soundcloud.*"],
        }
        with YoutubeDL(params) as ydl:
            info = ydl.extract_info(url, download=False)
        if info:
            for entry in info.get("entries") or []:
                if entry and entry.get("id"):
                    ids.append(str(entry["id"]))
        return ids
    except Exception:
        return None


_FULL_SYNC = "full"
_SKIP = "skip"


def _fast_path(url: str) -> str | int:
    """
    Determine the sync strategy for this playlist.

    Returns:
      _FULL_SYNC  — run a full scdl --sync (new playlist, sanity failure, or --force-all)
      _SKIP       — nothing new, skip entirely
      int N       — run scdl with -o N (start downloading from position N)

    Algorithm (assumes new tracks are appended to the END of the playlist):
      1. N = number of tracks in the local archive (= songs we already have).
      2. Fetch the first _SANITY_N SC track IDs (the oldest songs in the playlist).
         They should all be in the archive. If none match, the playlist may have been
         replaced or drastically reshuffled → full sync.
      3. Check whether position N+1 exists on SC.
         No  → playlist unchanged → skip.
         Yes → new songs start at N+1 → run scdl with -o N+1.
    """
    known = _archive_ids(url)
    N = len(known)
    if N == 0:
        return _FULL_SYNC  # new playlist

    # Sanity check: oldest songs (positions 1.._SANITY_N) should be in archive
    heads = _fetch_ids_at(url, f"1:{_SANITY_N}")
    if heads is None:
        return _FULL_SYNC  # pre-scan failed
    if not any(tid in known for tid in heads):
        return _FULL_SYNC  # none of first 3 recognised → playlist mismatch

    # Check if a new song exists at position N+1
    next_ids = _fetch_ids_at(url, f"{N + 1}:{N + 1}")
    if next_ids is None:
        return _FULL_SYNC  # check failed
    if not next_ids:
        return _SKIP  # nothing at N+1 → playlist unchanged

    return N + 1  # new songs start here


# ---------------------------------------------------------------------------
# Output filtering
# ---------------------------------------------------------------------------

_SHOW_STARTS = ("ERROR:", "WARNING:")
_SHOW_IN = ("[download] Destination:", "Playlist renamed")
_HIDE_STARTS = (
    "[soundcloud]", "[info]", "[debug]", "[MutagenPP]", "[Merger]",
    "[ExtractAudio]", "[ThumbnailsConvertor]", "[ThumbnailPP]",
    "[FixupM4a]", "[Mutagen]", "[FixupM3u8]", "[EmbedThumbnail]", "[FFmpegMetadata]",
)
_HIDE_IN = (
    "SCDL version", "Generating dynamic client_id", "Sync archive:",
    "Invalid client_id", "dynamically generated", "[download] 100%",
    "Using a dynamically generated",
    "has already been recorded in the archive", "has already been downloaded",
)

# ERROR: lines that are expected noise (deleted/unavailable tracks) — suppressed unless --verbose
_SUPPRESS_ERRORS = (
    "Unable to download JSON metadata: HTTP Error 404",
)


def _show(line: str) -> bool:
    if _verbose:
        return bool(line.strip())
    s = line.strip()
    if not s:
        return False
    if any(s.startswith(p) for p in _SHOW_STARTS):
        if any(sub in s for sub in _SUPPRESS_ERRORS):
            return False
        return True
    if any(sub in s for sub in _SHOW_IN):
        return True
    if any(s.startswith(p) for p in _HIDE_STARTS):
        return False
    if any(sub in s for sub in _HIDE_IN):
        return False
    return True


# ---------------------------------------------------------------------------
# scdl runner
# ---------------------------------------------------------------------------

_BASE_YT_DLP_ARGS = " ".join([
    "--sleep-requests 1",
    "--extractor-retries 5",
    "--retry-sleep extractor:60",
])

_CONN_ERRORS = [
    "ConnectionError:", "curl: (7)", "ClientIDGenerationError:", "No asset scripts found",
]


def run_scdl(
    url: str,
    max_errors: int,
    force_all: bool = False,
    write=None,
) -> tuple[bool, bool, bool, list[str], dict]:
    """
    Returns (success, aborted, is_conn_error, error_lines, stats).
    stats: {"downloaded": int, "skipped": bool}
      skipped=True means the fast-path determined nothing is new (no scdl run).

    write: callable for printing filtered output lines (default: print).
           Pass tqdm.write when inside a tqdm loop so lines appear above the bar.
    """
    if write is None:
        write = print

    strategy = _FULL_SYNC if force_all else _fast_path(url)

    if strategy == _SKIP:
        return True, False, False, [], {"downloaded": 0, "skipped": True}

    cmd = [
        "scdl", "-l", url, "--sync", "--path", str(SC_PLAYLIST_DIR),
        "--hide-progress", "--yt-dlp-args", _BASE_YT_DLP_ARGS,
    ]
    if isinstance(strategy, int):
        # Start from position N+1. SyncDownloadHelper sees -o is set and marks
        # all archive entries not downloaded this run as "not evaluated", so they
        # are preserved rather than falsely marked [unsync].
        cmd += ["-o", str(strategy)]

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )

    has_error = False
    consecutive_errors = 0
    aborted = False
    is_conn_error = False
    error_lines: list[str] = []
    downloaded = 0

    for line in proc.stdout:
        if any(m in line for m in _CONN_ERRORS):
            is_conn_error = True

        if line.startswith("ERROR:"):
            has_error = True
            consecutive_errors += 1
            error_lines.append(line.rstrip())
            if consecutive_errors >= max_errors:
                write(f"  [abort] {consecutive_errors} consecutive errors — rate limited.")
                proc.terminate()
                try:
                    proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                aborted = True
                break
        elif "[soundcloud]" in line or "[download] Destination:" in line:
            # Reset on any successfully-processed track, not just active downloads.
            # Prevents scattered errors across a large already-synced playlist from
            # triggering the abort as if they were truly consecutive.
            consecutive_errors = 0

        if "[download] Destination:" in line:
            downloaded += 1

        if _show(line):
            write(line.rstrip())

    proc.wait()
    success = proc.returncode == 0 and not has_error
    return success, aborted, is_conn_error, error_lines, {"downloaded": downloaded, "skipped": False}


# ---------------------------------------------------------------------------
# Sync loop
# ---------------------------------------------------------------------------

def sync_list(
    urls: list[str],
    delay: float,
    max_errors: int,
    force_all: bool,
    track_state: bool = False,
    label: str = "",
    _state_urls: list[str] | None = None,
    _state_offset: int = 0,
) -> list[str]:
    """Sync URLs in order. Returns list of failed URLs."""
    failed: list[str] = []
    total = len(urls)

    with tqdm(total=total, desc=f"{label}playlists", unit="pl", dynamic_ncols=True) as pbar:
        for i, url in enumerate(urls, 1):
            lbl = _label(url)
            pbar.set_description(f"{label}{lbl[:50]}")
            tqdm.write(f"\n[{i}/{total}] {lbl}")

            t0 = time.time()
            ok, aborted, is_conn_error, error_lines, stats = run_scdl(
                url, max_errors, force_all, write=tqdm.write,
            )
            elapsed = time.time() - t0

            if stats["skipped"]:
                tqdm.write("  → up to date")
            else:
                parts: list[str] = []
                if stats["downloaded"]:
                    parts.append(f"{stats['downloaded']} downloaded")
                if error_lines:
                    parts.append(f"{len(error_lines)} error(s)")
                tqdm.write(f"  → {', '.join(parts) or 'nothing new'} ({elapsed:.0f}s)")

            if not ok:
                failed.append(url)

            pbar.update(1)

            if track_state and not is_conn_error:
                _save_state(_state_urls if _state_urls is not None else urls, _state_offset + i)

            if is_conn_error:
                rest = urls[i:]
                if rest:
                    tqdm.write(f"\n  [sync] IP block — skipping {len(rest)} remaining.")
                    failed.extend(rest)
                break

            if i < total:
                if aborted:
                    tqdm.write(f"\n  [sync] Rate limit — cooling down {RATE_LIMIT_COOLDOWN}s...")
                    time.sleep(RATE_LIMIT_COOLDOWN)
                elif delay > 0:
                    wait = delay * random.uniform(0.5, 1.5)
                    tqdm.write(f"  Waiting {wait:.1f}s... ({total - i} remaining)")
                    time.sleep(wait)

    return failed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    global _verbose
    args = parse_args()
    _verbose = args.verbose

    raw_urls = [
        line.strip()
        for line in PLAYLIST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("http")
    ]
    if not raw_urls:
        print("No URLs found in sc-playlists-list.md")
        sys.exit(1)

    # Resume support
    if args.resume:
        state = _load_state()
        if state and state.get("completed", 0) < len(state.get("urls", [])):
            all_urls = state["urls"]
            done = state["completed"]
            remaining = all_urls[done:]
            print(f"Resuming from {done + 1}/{len(all_urls)} ({len(remaining)} remaining).\n")
            failed = sync_list(
                remaining, args.delay, args.max_errors, args.force_all,
                track_state=True, _state_urls=all_urls, _state_offset=done,
            )
            _finalize(failed)
            return
        print("No interrupted run found — starting fresh.\n")
        _clear_state()

    # Indices = line order in sc-playlists-list.md (line 1 = --only 1, no sorting)
    if args.only:
        only_set = set(args.only)
        to_run = [u for j, u in enumerate(raw_urls, 1) if j in only_set]
    else:
        skip_set: set[int] = set(args.skip or [])
        if args.from_index:
            skip_set |= set(range(1, args.from_index))
        to_run = [u for j, u in enumerate(raw_urls, 1) if j not in skip_set]

    if not to_run:
        print("No playlists to sync after applying filters.")
        sys.exit(0)

    mode = "full sync (--force-all)" if args.force_all else f"fast-path (sanity {_SANITY_N} + frontier check)"
    print(f"Syncing {len(to_run)}/{len(raw_urls)} playlist(s) — {mode}")
    print(f"  delay: {args.delay}s ±50% | max-errors: {args.max_errors}\n")
    run_set = set(to_run)
    for j, u in enumerate(raw_urls, 1):
        marker = "→" if u in run_set else " "
        print(f"  {marker} {j:2}. {_label(u)}")
    print()

    _save_state(to_run, 0)
    failed = sync_list(to_run, args.delay, args.max_errors, args.force_all, track_state=True)
    _finalize(failed)


_FAIL_TAG_RE = re.compile(r"^\[FAIL\]", re.MULTILINE)


def _failed_playlist_stems(urls: list[str]) -> list[str]:
    """Stems of playlists whose .failed file has at least one [FAIL] entry
    (DRM-protected etc.) — re-running scdl won't fix those, but YouTube recovery
    might. [FOUND]/[GO+]/[BLOCKED]/[MONETIZE] entries are left out: retry_failed_with_ytdl.py
    only acts on [FAIL], and a file with only those tags has nothing for it to do."""
    stems = []
    for u in urls:
        failed_path = archive_path(u).with_suffix(".failed")
        if not failed_path.exists():
            continue
        if _FAIL_TAG_RE.search(failed_path.read_text(encoding="utf-8", errors="replace")):
            stems.append(archive_path(u).stem)
    return stems


def _run_youtube_retry(urls: list[str]) -> None:
    stems = _failed_playlist_stems(urls)
    if not stems:
        print("\nNo track-level failures to recover via YouTube.")
        return
    script = _ROOT / "src" / "retry_failed_with_ytdl.py"
    for stem in stems:
        print(f"\n--- {stem} ---")
        subprocess.run([sys.executable, str(script), stem], check=False)


def _finalize(failed: list[str]) -> None:
    if not failed:
        print("\nAll done.")
        _clear_state()
        return

    print(f"\n{len(failed)} playlist(s) failed:")
    for u in failed:
        print(f"  {u}")

    try:
        answer = input("\nWant to try recovering failed tracks via YouTube instead? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""

    if answer == "y":
        _run_youtube_retry(failed)

    sys.exit(1)


if __name__ == "__main__":
    main()
