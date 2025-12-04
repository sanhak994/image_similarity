from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


WORK_DIR = Path(__file__).resolve().parent.parent / "work"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export helpers")
    parser.add_argument("--mode", choices=["missing", "keepers"], required=True)
    parser.add_argument("--source", required=True, help="Source library path")
    parser.add_argument("--other", help="Other library path (for missing mode)")
    parser.add_argument("--dest", required=True, help="Export destination directory")
    parser.add_argument("--log", help="Review log (for keepers)")
    return parser.parse_args()


def _load_hashes(label: str) -> list[dict]:
    path = WORK_DIR / f"{label}_hashes.json"
    if not path.exists():
        raise FileNotFoundError(f"Hashes not found: {path}")
    return json.loads(path.read_text())


def _load_review_log(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    import csv

    deletes = set()
    with log_path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("delete_library") == "photos" and row.get("delete_uuid"):
                deletes.add(row["delete_uuid"])
            other = row.get("delete_uuid_other")
            other_lib = row.get("delete_library_other")
            if other and other_lib == "photos":
                deletes.add(other)
    return deletes


def _copy_unique(src_path: Path, dest_dir: Path) -> Path | None:
    if not src_path.exists():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / src_path.name
    counter = 1
    while target.exists():
        target = dest_dir / f"{src_path.stem}_{counter}{src_path.suffix}"
        counter += 1
    shutil.copy2(src_path, target)
    return target


def export_missing(source_label: str, other_label: str, dest: Path):
    src_hashes = _load_hashes(source_label)
    other_hashes = _load_hashes(other_label)
    other_set = {item["hash_int"] for item in other_hashes}

    missing = [item for item in src_hashes if item["hash_int"] not in other_set]
    total = len(missing)
    copied = 0
    for item in missing:
        src_path = Path(item["path"])
        out = _copy_unique(src_path, dest)
        if out:
            copied += 1
        print(f"PROGRESS {copied}/{total}", flush=True)
    print(f"Exported {copied} of {total} missing items to {dest}", flush=True)


def export_keepers(source_label: str, dest: Path, log_path: Path):
    src_hashes = _load_hashes(source_label)
    deletes = _load_review_log(log_path)
    keepers = [item for item in src_hashes if item["uuid"] not in deletes]
    total = len(keepers)
    copied = 0
    for item in keepers:
        src_path = Path(item["path"])
        out = _copy_unique(src_path, dest)
        if out:
            copied += 1
        print(f"PROGRESS {copied}/{total}", flush=True)
    print(f"Exported {copied} of {total} keepers to {dest}", flush=True)


def detect_label(lib_path: str) -> str:
    lib = lib_path.lower()
    if lib.endswith(".photoslibrary"):
        return "photos"
    if lib.endswith(".photolibrary"):
        return "iphoto"
    raise ValueError("Unknown library type; expected .photoslibrary or .photolibrary")


def main():
    args = parse_args()
    dest = Path(args.dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)

    if args.mode == "missing":
        src_label = detect_label(args.source)
        other_label = detect_label(args.other or "")
        export_missing(src_label, other_label, dest)
    elif args.mode == "keepers":
        src_label = detect_label(args.source)
        log_path = Path(args.log) if args.log else WORK_DIR / "review_log.csv"
        export_keepers(src_label, dest, log_path)
    else:
        print("Unknown mode", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
