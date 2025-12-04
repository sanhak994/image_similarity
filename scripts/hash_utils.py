from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple


class HashComputationError(Exception):
    """Raised when an image hash cannot be computed."""


def _lazy_import_image_libs():
    try:
        import warnings
        from PIL import Image

        # allow large images but surface decompression warnings
        Image.MAX_IMAGE_PIXELS = None
        warnings.simplefilter("default")
        try:
            from PIL import Image as _Img
            if hasattr(_Img, "DecompressionBombWarning"):
                warnings.simplefilter("default", _Img.DecompressionBombWarning)
        except Exception:
            pass
    except ImportError as exc:  # pragma: no cover - dependency missing in sandbox
        raise HashComputationError(
            "pillow is required. Install with: pip install pillow"
        ) from exc

    try:
        import imagehash
    except ImportError as exc:  # pragma: no cover - dependency missing in sandbox
        raise HashComputationError(
            "ImageHash is required. Install with: pip install ImageHash"
        ) from exc

    return Image, imagehash


SUPPORTED_METHODS = {"phash", "ahash", "dhash", "whash"}


def hamming_distance_int(a: int, b: int) -> int:
    """Fast Hamming distance for integer hashes."""
    return (a ^ b).bit_count()


def _convert_with_sips(image_path: Path, temp_dir: Path | None) -> Path | None:
    """Convert an image to JPEG using sips when Pillow cannot open it (e.g., HEIC)."""
    temp_dir = temp_dir or Path(tempfile.gettempdir())
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkstemp(suffix=".jpg", dir=temp_dir)[1])

    result = subprocess.run(
        ["sips", "-s", "format", "jpeg", str(image_path), "--out", str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and target.exists():
        return target

    if target.exists():
        target.unlink()
    return None


def _open_image(image_path: Path, temp_dir: Path | None):
    """Open an image with Pillow, falling back to sips conversion if needed."""
    Image, _ = _lazy_import_image_libs()
    try:
        return Image.open(image_path)
    except Exception:
        converted = _convert_with_sips(image_path, temp_dir)
        if not converted:
            raise
        return Image.open(converted)


def compute_perceptual_hash(
    image_path: str | Path,
    method: str = "phash",
    hash_size: int = 16,
    temp_dir: str | Path | None = None,
) -> Tuple[str, int, int]:
    """Compute a perceptual hash for an image.

    Returns:
        tuple of (hash_hex, hash_int, bit_length)
    """
    Image, imagehash = _lazy_import_image_libs()

    method = method.lower()
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unsupported hash method '{method}'. Choose from {SUPPORTED_METHODS}.")

    img_path = Path(image_path).expanduser().resolve()
    if not img_path.exists():
        raise FileNotFoundError(f"Image not found: {img_path}")

    with _open_image(img_path, Path(temp_dir) if temp_dir else None) as img:
        img = img.convert("RGB")
        hash_fn = getattr(imagehash, method)
        hash_obj = hash_fn(img, hash_size=hash_size)

    hash_hex = str(hash_obj)
    hash_int = int(hash_hex, 16)
    bit_length = hash_obj.hash.size
    return hash_hex, hash_int, bit_length
