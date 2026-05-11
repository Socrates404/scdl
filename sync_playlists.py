#!/usr/bin/env python3
import argparse
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

PLAYLIST_FILE = Path(__file__).parent / "playlists-list.md"
ARCHIVE_DIR = Path(__file__).parent / "archive_trackers"
RATE_LIMIT_COOLDOWN = 120  # seconds to wait after detecting a rate-limit burst
RETRY_DELAY = 30           # seconds between retries


def parse_args():
    parser = argparse.ArgumentParser(description="Sync all playlists in playlists-list.md")
    parser.add_argument(
        "--delay",
        type=float,
        default=8.0,
        metavar="SECONDS",
        help="Base delay between playlists (default: 8s, actual = delay ± 50%% jitter)",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=5,
        metavar="N",
        help="Abort a playlist after N consecutive track errors (rate-limit guard, default: 5)",
    )
    return parser.parse_args()


def archive_path(url: str) -> Path:
    """Mirrors scdl's archive filename derivation from a playlist URL."""
    url_path = urlparse(url).path.strip("/")
    parts = [p for p in url_path.split("/") if p != "sets"]
    archive_name = "_".join(parts) if parts else "unknown"
    return ARCHIVE_DIR / f"{archive_name}.txt"


def is_empty(path: Path) -> bool:
    return not path.exists() or path.stat().st_size == 0


def sort_urls(urls: list[str]) -> list[str]:
    """Empty/missing archives first (both groups shuffled internally)."""
    empty, populated = [], []
    for url in urls:
        (empty if is_empty(archive_path(url)) else populated).append(url)
    random.shuffle(empty)
    random.shuffle(populated)
    return empty + populated


YT_DLP_ARGS = " ".join([
    "--sleep-requests 1",       # 1s between API calls → stays under 600 req/10min
    "--extractor-retries 5",    # retry up to 5× on 429
    "--retry-sleep extractor:60",  # wait 60s between retries (lets the window clear)
])


def run_scdl(url: str, max_errors: int) -> tuple[bool, bool, list[str]]:
    """
    Run scdl --sync for a URL.
    Returns (success, was_aborted, error_lines).
    """
    proc = subprocess.Popen(
        ["scdl", "-l", url, "--sync", "--yt-dlp-args", YT_DLP_ARGS],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    has_error = False
    consecutive_errors = 0
    aborted = False
    error_lines: list[str] = []

    for line in proc.stdout:
        print(line, end="", flush=True)

        if line.startswith("ERROR:"):
            has_error = True
            consecutive_errors += 1
            error_lines.append(line.rstrip())
            if consecutive_errors >= max_errors:
                print(
                    f"\n  [sync] {consecutive_errors} consecutive track errors — "
                    f"rate limited. Aborting playlist early.",
                    flush=True,
                )
                proc.terminate()
                try:
                    proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                aborted = True
                break
        elif "[download]" in line and "%" in line:
            consecutive_errors = 0

    proc.wait()
    success = proc.returncode == 0 and not has_error
    return success, aborted, error_lines


def errors_log_path(url: str) -> Path:
    return archive_path(url).with_suffix(".errors.log")


def sync_list(urls: list[str], delay: float, max_errors: int, label: str = "") -> list[str]:
    """Sync a list of URLs with delay between each. Returns list of failed URLs."""
    failed = []
    total = len(urls)

    for i, url in enumerate(urls, 1):
        prefix = f"{label}[{i}/{total}]" if label else f"[{i}/{total}]"
        print(f"{prefix} {url}")

        ok, aborted, error_lines = run_scdl(url, max_errors)

        if not ok:
            failed.append(url)

        if error_lines:
            log = errors_log_path(url)
            log.parent.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with log.open("a", encoding="utf-8") as f:
                f.write(f"\n--- {timestamp}  {url} ---\n")
                for line in error_lines:
                    f.write(line + "\n")

        print()

        if i < total:
            if aborted:
                print(
                    f"  [sync] Rate limit detected — cooling down for {RATE_LIMIT_COOLDOWN}s "
                    f"before next playlist...\n"
                )
                time.sleep(RATE_LIMIT_COOLDOWN)
            elif delay > 0:
                actual = delay * random.uniform(0.5, 1.5)
                remaining = total - i
                print(f"  Waiting {actual:.1f}s before next playlist ({remaining} remaining)...\n")
                time.sleep(actual)

    return failed


def main():
    args = parse_args()

    raw_urls = [
        line.strip()
        for line in PLAYLIST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("http")
    ]

    if not raw_urls:
        print("No URLs found in playlists-list.md")
        sys.exit(1)

    urls = sort_urls(raw_urls)

    empty_count = sum(1 for u in urls if is_empty(archive_path(u)))
    print(
        f"Syncing {len(urls)} playlists "
        f"({empty_count} empty/new first, then {len(urls) - empty_count} already-populated, "
        f"both groups shuffled).\n"
        f"Delay: {args.delay}s ± 50% jitter | max-errors: {args.max_errors}\n"
    )

    failed = sync_list(urls, args.delay, args.max_errors)

    if not failed:
        print(f"Done. All {len(urls)} playlists synced successfully.")
        _print_error_log_summary(urls)
        return

    print(f"\n{len(failed)} playlist(s) failed. Waiting 60s before retrying...\n")
    time.sleep(60)

    still_failed = sync_list(failed, delay=RETRY_DELAY, max_errors=args.max_errors, label="RETRY ")

    if still_failed:
        print(f"\nDone. {len(still_failed)} playlist(s) failed after retry:")
        for url in still_failed:
            print(f"  {url}")
        _print_error_log_summary(urls)
        sys.exit(1)
    else:
        print(f"\nDone. All playlists synced successfully (some needed a retry).")
        _print_error_log_summary(urls)


def _print_error_log_summary(urls: list[str]) -> None:
    logs_with_errors = [errors_log_path(url) for url in urls if errors_log_path(url).exists()]
    if not logs_with_errors:
        return
    print(f"\n{len(logs_with_errors)} playlist(s) have error logs:")
    for log in logs_with_errors:
        print(f"  {log}")


if __name__ == "__main__":
    main()
