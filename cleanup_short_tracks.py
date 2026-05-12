"""
Delete audio files in ./playlists that are 30 seconds or shorter.
These are SoundCloud GO+ preview snips, not full tracks.

Usage:
    python cleanup_short_tracks.py           # dry run, lists what would be deleted
    python cleanup_short_tracks.py --delete  # actually deletes the files
"""

import sys
from pathlib import Path

from mutagen import File as MutagenFile

PLAYLIST_DIR = Path(__file__).parent / "playlists"
MAX_DURATION = 30  # seconds — SoundCloud snips are exactly 30s
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".opus", ".flac", ".wav", ".ogg"}

dry_run = "--delete" not in sys.argv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def get_duration(path: Path) -> float | None:
    audio = MutagenFile(path)
    if audio is None or audio.info is None:
        return None
    return audio.info.length


def main() -> None:
    if dry_run:
        print("Dry run — pass --delete to actually remove files.\n")

    short_files: list[Path] = []

    for ext in AUDIO_EXTENSIONS:
        for f in PLAYLIST_DIR.rglob(f"*{ext}"):
            duration = get_duration(f)
            if duration is None:
                print(f"  [skip] Could not read duration: {f.name}")
                continue
            if duration <= MAX_DURATION:
                short_files.append(f)
                status = "DELETED" if not dry_run else "would delete"
                print(f"  [{status}] {duration:.1f}s  {f.relative_to(PLAYLIST_DIR)}")
                if not dry_run:
                    f.unlink()

    print(f"\n{'Would remove' if dry_run else 'Removed'} {len(short_files)} file(s).")


if __name__ == "__main__":
    main()
