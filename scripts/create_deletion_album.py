from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Set

# Ensure local imports work when run as a script.
if __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parent))

from photoscript import Photo, PhotosLibrary


def _load_deletions(log_path: Path) -> Set[str]:
    with log_path.open() as f:
        reader = csv.DictReader(f)
        return {
            row["delete_uuid"]
            for row in reader
            if row.get("delete_library") == "photos"
            and row.get("decision") in {"keep_left", "keep_right"}
            and row.get("delete_uuid")
        }


def _get_or_create_album(lib: PhotosLibrary, name: str):
    for album in lib.albums():
        if album.name == name:
            return album
    return lib.create_album(name)


def chunked(seq: List[str], size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add photos marked for deletion to a Photos album."
    )
    parser.add_argument(
        "--log",
        required=True,
        help="Decision log produced by review_pairs.py.",
    )
    parser.add_argument(
        "--album-name",
        help="Album to place deletion candidates into. Defaults to 'To Delete <date>'.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Number of photos to add per AppleScript batch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print UUIDs without modifying Photos.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    log_path = Path(args.log)
    if not log_path.exists():
        print(f"Review log not found at {log_path}. Run a review before creating the album.")
        return

    delete_uuids = sorted(_load_deletions(log_path))
    if not delete_uuids:
        print("No Photos library items flagged for deletion.")
        return

    album_name = args.album_name or f"To Delete {datetime.now().date().isoformat()}"
    if args.dry_run:
        print(f"[dry-run] Would add {len(delete_uuids)} items to album '{album_name}'")
        return

    lib = PhotosLibrary()
    album = _get_or_create_album(lib, album_name)
    added = 0
    missing = 0

    for batch in chunked(delete_uuids, args.batch_size):
        photos = []
        for uuid in batch:
            try:
                photos.append(Photo(uuid))
            except Exception:
                missing += 1
        if photos:
            album.add(photos)
            added += len(photos)

    print(f"Added {added} photos to album '{album.name}'.")
    if missing:
        print(f"Skipped {missing} UUIDs that were not found in the current library.")


if __name__ == "__main__":
    main()
