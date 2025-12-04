from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure local imports work when run as a script.
if __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parent))

from bktree import BKTree
from hash_utils import SUPPORTED_METHODS, hamming_distance_int
from photo_library import PhotoRecord, load_library_records


def _write_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(payload, f, indent=2)


def _dedupe_pairs(pairs: List[Tuple[PhotoRecord, PhotoRecord, int]]) -> List[
    Tuple[PhotoRecord, PhotoRecord, int]
]:
    seen = set()
    deduped = []
    for left, right, dist in pairs:
        key = tuple(sorted([left.uuid, right.uuid]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append((left, right, dist))
    return deduped


def _build_pairs(
    photos_records: List[PhotoRecord],
    iphoto_records: List[PhotoRecord],
    dupe_threshold: int,
    cross_threshold: int,
) -> Tuple[List[dict], List[dict]]:
    pairs: List[Tuple[PhotoRecord, PhotoRecord, int]] = []
    photos_dupe_pairs: List[Tuple[PhotoRecord, PhotoRecord, int]] = []
    unique_iphoto: List[dict] = []

    # intra-Photos duplicates
    photos_tree = BKTree(hamming_distance_int)
    for rec in photos_records:
        for other, dist in photos_tree.query(rec.hash_int, dupe_threshold):
            photos_dupe_pairs.append((rec, other, dist))
        photos_tree.add(rec.hash_int, rec)

    photos_dupe_pairs = _dedupe_pairs(photos_dupe_pairs)

    # cross-library similarity
    if iphoto_records:
        cross_tree = BKTree(hamming_distance_int)
        for rec in photos_records:
            cross_tree.add(rec.hash_int, rec)

        for ip_rec in iphoto_records:
            matches = cross_tree.query(ip_rec.hash_int, cross_threshold)
            if not matches:
                unique_iphoto.append(ip_rec.asdict())
                continue
            for other, dist in matches:
                pairs.append((ip_rec, other, dist))

    pairs = _dedupe_pairs(pairs)

    combined_pairs: List[dict] = []
    pair_id = 1
    for rec_a, rec_b, dist in sorted(
        photos_dupe_pairs + pairs, key=lambda triple: triple[2]
    ):
        pair_type = "photos_dupe" if rec_a.library == rec_b.library else "cross_library"
        combined_pairs.append(
            {
                "pair_id": pair_id,
                "pair_type": pair_type,
                "distance": dist,
                "hash_method": rec_a.hash_method,
                "hash_bits": rec_a.hash_bits,
                "library_left": rec_a.library,
                "uuid_left": rec_a.uuid,
                "path_left": rec_a.path,
                "filename_left": rec_a.filename,
                "library_right": rec_b.library,
                "uuid_right": rec_b.uuid,
                "path_right": rec_b.path,
                "filename_right": rec_b.filename,
            }
        )
        pair_id += 1

    return combined_pairs, unique_iphoto


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find similar/duplicate photos across Photos and iPhoto libraries."
    )
    parser.add_argument(
        "--photos-lib",
        required=True,
        help="Path to the Photos library (.photoslibrary).",
    )
    parser.add_argument(
        "--iphoto-lib",
        help="Path to the iPhoto library (.photolibrary). Optional; skip cross-library matching if omitted.",
    )
    parser.add_argument(
        "--hash-method",
        default="phash",
        choices=sorted(SUPPORTED_METHODS),
        help="Perceptual hash method.",
    )
    parser.add_argument(
        "--hash-size",
        type=int,
        default=16,
        help="Hash size for perceptual hash function.",
    )
    parser.add_argument(
        "--threshold-dupes",
        type=int,
        default=5,
        help="Max Hamming distance to consider Photos-library items as duplicates.",
    )
    parser.add_argument(
        "--threshold-cross",
        type=int,
        default=8,
        help="Max Hamming distance to consider iPhoto items similar to Photos.",
    )
    parser.add_argument(
        "--prefer-edited",
        action="store_true",
        help="Hash edited versions when available instead of originals.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Thread workers for hashing.",
    )
    parser.add_argument(
        "--temp-dir",
        help="Optional directory for temporary conversions (e.g., HEIC -> JPEG).",
    )
    return parser.parse_args()


def main():
    import warnings

    warnings.simplefilter("default")
    args = parse_args()
    output_dir = Path("work")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Hashing Photos library...")
    def progress_photos(done, total):
        print(f"PROGRESS {done}/{total}", flush=True)

    photos_records, photos_errors = load_library_records(
        args.photos_lib,
        library_label="photos",
        hash_method=args.hash_method,
        hash_size=args.hash_size,
        prefer_edited=args.prefer_edited,
        max_workers=args.workers,
        temp_dir=args.temp_dir,
        progress_cb=progress_photos,
    )

    iphoto_records: List[PhotoRecord] = []
    iphoto_errors: List[tuple] = []
    if args.iphoto_lib:
        print("Hashing iPhoto library...")
        def progress_iphoto(done, total):
            print(f"PROGRESS {done}/{total}", flush=True)

        iphoto_records, iphoto_errors = load_library_records(
            args.iphoto_lib,
            library_label="iphoto",
            hash_method=args.hash_method,
            hash_size=args.hash_size,
            prefer_edited=args.prefer_edited,
            max_workers=args.workers,
            temp_dir=args.temp_dir,
            progress_cb=progress_iphoto,
        )

    print("Building candidate pairs...")
    pairs, unique_iphoto = _build_pairs(
        photos_records,
        iphoto_records,
        dupe_threshold=args.threshold_dupes,
        cross_threshold=args.threshold_cross,
    )

    pair_path = output_dir / "pairs_for_review.csv"
    unique_path = output_dir / "unique_in_iphoto.csv"
    hashes_photos_path = output_dir / "photos_hashes.json"
    hashes_iphoto_path = output_dir / "iphoto_hashes.json"
    error_path = output_dir / "hash_errors.log"

    _write_csv(
        pair_path,
        pairs,
        fieldnames=[
            "pair_id",
            "pair_type",
            "distance",
            "hash_method",
            "hash_bits",
            "library_left",
            "uuid_left",
            "path_left",
            "filename_left",
            "library_right",
            "uuid_right",
            "path_right",
            "filename_right",
        ],
    )

    if unique_iphoto:
        _write_csv(
            unique_path,
            unique_iphoto,
            fieldnames=list(unique_iphoto[0].keys()),
        )

    _write_json(
        hashes_photos_path,
        [rec.asdict() for rec in photos_records],
    )
    if iphoto_records:
        _write_json(
            hashes_iphoto_path,
            [rec.asdict() for rec in iphoto_records],
        )

    # write errors
    if photos_errors or iphoto_errors:
        error_lines = []
        for uuid, reason in photos_errors:
            error_lines.append(f"photos,{uuid},{reason}")
        for uuid, reason in iphoto_errors:
            error_lines.append(f"iphoto,{uuid},{reason}")
        error_path.write_text("\n".join(error_lines))

    print(f"Pairs written to {pair_path}")
    if unique_iphoto:
        print(f"Likely unique iPhoto items: {unique_path}")
    if photos_errors or iphoto_errors:
        print(f"Hashing errors logged to {error_path}")


if __name__ == "__main__":
    main()
