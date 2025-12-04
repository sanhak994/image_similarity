from __future__ import annotations

import logging
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Tuple

from osxphotos import PhotosDB
from osxphotos.iphoto import iPhotoDB

# Support running as a script (no package context).
if __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parent))

from hash_utils import HashComputationError, compute_perceptual_hash

logger = logging.getLogger(__name__)


@dataclass
class PhotoRecord:
    library: str
    uuid: str
    path: str
    filename: str
    date: str
    is_raw: bool
    is_missing: bool
    width: int | None
    height: int | None
    hash_hex: str
    hash_int: int
    hash_bits: int
    hash_method: str

    def asdict(self) -> dict:
        return asdict(self)


def _select_path(photo, prefer_edited: bool = False) -> str | None:
    """Pick the best on-disk path for a photo."""
    candidates: list[str | None] = []
    if prefer_edited:
        candidates.extend(
            [
                getattr(photo, "path_edited", None),
                getattr(photo, "path", None),
                getattr(photo, "path_raw", None),
            ]
        )
    else:
        candidates.extend(
            [
                getattr(photo, "path", None),
                getattr(photo, "path_edited", None),
                getattr(photo, "path_raw", None),
            ]
        )

    derivatives = getattr(photo, "path_derivatives", [])
    if derivatives:
        candidates.extend(derivatives if isinstance(derivatives, list) else [derivatives])

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def _date_to_str(date_obj) -> str:
    if not date_obj:
        return ""
    try:
        return date_obj.isoformat()
    except Exception:
        return str(date_obj)


def _iter_photos(db) -> Iterable:
    """Return iterable of photos for PhotosDB or iPhotoDB."""
    try:
        return db.photos()
    except TypeError:
        # iPhotoDB.photos may require keyword args; default to all
        return db.photos(images=True, movies=True)


def _process_photo(
    photo,
    library_label: str,
    hash_method: str,
    hash_size: int,
    prefer_edited: bool,
    temp_dir: Path | None,
) -> Tuple[PhotoRecord | None, str | None]:
    is_movie = bool(getattr(photo, "ismovie", False))
    is_photo = bool(getattr(photo, "isphoto", True))
    if is_movie or not is_photo:
        return None, "skip-non-photo"

    if getattr(photo, "ismissing", False):
        return None, "missing-from-disk"

    photo_path = _select_path(photo, prefer_edited=prefer_edited)
    if not photo_path:
        return None, "no-path"

    try:
        hash_hex, hash_int, bit_length = compute_perceptual_hash(
            photo_path, method=hash_method, hash_size=hash_size, temp_dir=temp_dir
        )
    except (HashComputationError, FileNotFoundError) as exc:
        return None, f"hash-error:{exc}"
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"hash-error:{exc}"

    record = PhotoRecord(
        library=library_label,
        uuid=photo.uuid,
        path=photo_path,
        filename=getattr(photo, "original_filename", getattr(photo, "filename", "")),
        date=_date_to_str(getattr(photo, "date", None)),
        is_raw=bool(getattr(photo, "israw", False)),
        is_missing=bool(getattr(photo, "ismissing", False)),
        width=getattr(photo, "width", None),
        height=getattr(photo, "height", None),
        hash_hex=hash_hex,
        hash_int=hash_int,
        hash_bits=bit_length,
        hash_method=hash_method,
    )
    return record, None


def _load_via_photosdb(
    db,
    library_label: str,
    hash_method: str,
    hash_size: int,
    prefer_edited: bool,
    max_workers: int,
    temp_dir: str | Path | None,
    progress_cb=None,
) -> Tuple[List[PhotoRecord], List[Tuple[str, str]]]:
    photos = list(_iter_photos(db))
    records: List[PhotoRecord] = []
    errors: List[Tuple[str, str]] = []
    temp_dir_path = Path(temp_dir) if temp_dir else None
    total = len(photos)
    processed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                _process_photo,
                photo,
                library_label,
                hash_method,
                hash_size,
                prefer_edited,
                temp_dir_path,
            ): photo
            for photo in photos
        }
        for future in as_completed(future_map):
            photo = future_map[future]
            try:
                record, error = future.result()
            except Exception as exc:  # pragma: no cover - defensive
                errors.append((getattr(photo, "uuid", "unknown"), f"exception:{exc}"))
                continue

            if error:
                errors.append((getattr(photo, "uuid", "unknown"), error))
                continue
            if record:
                records.append(record)
            processed += 1
            if progress_cb:
                progress_cb(processed, total)

    return records, errors


def load_library_records(
    db_path: str | Path,
    library_label: str,
    hash_method: str = "phash",
    hash_size: int = 16,
    prefer_edited: bool = False,
    max_workers: int = 4,
    temp_dir: str | Path | None = None,
    progress_cb=None,
) -> Tuple[List[PhotoRecord], List[Tuple[str, str]]]:
    """Load a Photos/iPhoto library and compute perceptual hashes.

    Returns:
        (records, errors) where errors is a list of (uuid, reason)
    """
    db_path = Path(db_path).expanduser().resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Library not found: {db_path}")

    if db_path.suffix == ".photoslibrary":
        db = PhotosDB(dbfile=str(db_path))
        return _load_via_photosdb(
            db,
            library_label,
            hash_method,
            hash_size,
            prefer_edited,
            max_workers,
            temp_dir,
            progress_cb,
        )

    db = iPhotoDB(dbfile=str(db_path))
    return _load_via_photosdb(
        db,
        library_label,
        hash_method,
        hash_size,
        prefer_edited,
        max_workers,
        temp_dir,
        progress_cb,
    )
