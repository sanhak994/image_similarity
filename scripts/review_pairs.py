from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import messagebox

# Ensure local imports work when run as a script.
if __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parent))

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - dependency guard
    print("pillow is required for the reviewer UI. Install with: pip install pillow")
    sys.exit(1)


def _load_pairs(csv_path: Path, filter_type: str | None = None) -> List[Dict]:
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        rows = [row for row in reader if not filter_type or row["pair_type"] == filter_type]
    for row in rows:
        row["pair_id"] = int(row["pair_id"])
        row["distance"] = int(row["distance"])
    rows.sort(key=lambda r: (r["pair_type"], r["distance"]))
    return rows


def _load_existing(log_path: Path) -> Dict[int, Dict]:
    if not log_path.exists():
        return {}
    with log_path.open() as f:
        reader = csv.DictReader(f)
        return {int(row["pair_id"]): row for row in reader}


def _convert_with_sips(image_path: Path) -> Optional[Path]:
    temp_target = Path(tempfile.mkstemp(suffix=".jpg")[1])
    result = subprocess.run(
        ["sips", "-s", "format", "jpeg", str(image_path), "--out", str(temp_target)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and temp_target.exists():
        return temp_target
    if temp_target.exists():
        temp_target.unlink()
    return None


def _open_image(path: Path) -> Optional[Image.Image]:
    if not path.exists():
        return None
    try:
        return Image.open(path)
    except Exception:
        converted = _convert_with_sips(path)
        if not converted:
            return None
        return Image.open(converted)


def _decision_payload(pair: Dict, decision: str) -> Dict:
    if decision == "keep_left":
        delete_uuid = pair["uuid_right"]
        delete_library = pair["library_right"]
        keep_uuid = pair["uuid_left"]
        keep_library = pair["library_left"]
    elif decision == "keep_right":
        delete_uuid = pair["uuid_left"]
        delete_library = pair["library_left"]
        keep_uuid = pair["uuid_right"]
        keep_library = pair["library_right"]
    else:
        delete_uuid = ""
        delete_library = ""
        keep_uuid = ""
        keep_library = ""

    return {
        "pair_id": pair["pair_id"],
        "pair_type": pair["pair_type"],
        "decision": decision,
        "distance": pair["distance"],
        "delete_uuid": delete_uuid,
        "delete_library": delete_library,
        "keep_uuid": keep_uuid,
        "keep_library": keep_library,
        "uuid_left": pair["uuid_left"],
        "uuid_right": pair["uuid_right"],
        "path_left": pair["path_left"],
        "path_right": pair["path_right"],
    }


class PairReviewer:
    def __init__(
        self,
        pairs: List[Dict],
        log_path: Path,
        start_index: int = 0,
        max_size: int = 1600,
    ) -> None:
        self.pairs = pairs
        self.log_path = log_path
        self.max_size = max_size
        self.index = start_index

        self.root = tk.Tk()
        self.root.title("Photo Pair Review")

        self.left_label = tk.Label(self.root)
        self.right_label = tk.Label(self.root)
        self.info_label = tk.Label(self.root, text="", font=("Arial", 12))
        self.left_label.grid(row=0, column=0, padx=10, pady=10)
        self.right_label.grid(row=0, column=1, padx=10, pady=10)
        self.info_label.grid(row=1, column=0, columnspan=2, pady=5)

        buttons = tk.Frame(self.root)
        buttons.grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(buttons, text="Keep Left (L)", command=lambda: self._choose("keep_left")).grid(
            row=0, column=0, padx=5
        )
        tk.Button(buttons, text="Keep Right (R)", command=lambda: self._choose("keep_right")).grid(
            row=0, column=1, padx=5
        )
        tk.Button(buttons, text="Skip (S)", command=lambda: self._choose("skip")).grid(
            row=0, column=2, padx=5
        )

        self.root.bind("<Left>", lambda _: self._choose("keep_left"))
        self.root.bind("<Right>", lambda _: self._choose("keep_right"))
        self.root.bind("s", lambda _: self._choose("skip"))
        self.root.bind("S", lambda _: self._choose("skip"))
        self.root.bind("<Escape>", lambda _: self.root.destroy())

        # Prepare log file with header if needed.
        if not log_path.exists():
            with log_path.open("w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "pair_id",
                        "pair_type",
                        "decision",
                        "distance",
                        "delete_uuid",
                        "delete_library",
                        "keep_uuid",
                        "keep_library",
                        "uuid_left",
                        "uuid_right",
                        "path_left",
                        "path_right",
                    ],
                )
                writer.writeheader()

        self._show_current()

    def _show_current(self) -> None:
        if self.index >= len(self.pairs):
            messagebox.showinfo("Done", "All pairs reviewed.")
            self.root.destroy()
            return

        pair = self.pairs[self.index]
        left_img = _open_image(Path(pair["path_left"]))
        right_img = _open_image(Path(pair["path_right"]))

        if left_img:
            left_img.thumbnail((self.max_size, self.max_size))
            self.left_photo = ImageTk.PhotoImage(left_img)
            self.left_label.config(image=self.left_photo, text="")
        else:
            self.left_label.config(text="Left image unavailable", image="")
            self.left_photo = None

        if right_img:
            right_img.thumbnail((self.max_size, self.max_size))
            self.right_photo = ImageTk.PhotoImage(right_img)
            self.right_label.config(image=self.right_photo, text="")
        else:
            self.right_label.config(text="Right image unavailable", image="")
            self.right_photo = None

        info = (
            f"Pair {pair['pair_id']} / {len(self.pairs)} | "
            f"type: {pair['pair_type']} | distance: {pair['distance']} | "
            f"left: {pair['filename_left']} | right: {pair['filename_right']}"
        )
        self.info_label.config(text=info)

    def _choose(self, decision: str) -> None:
        pair = self.pairs[self.index]
        payload = _decision_payload(pair, decision)
        with self.log_path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=payload.keys())
            writer.writerow(payload)

        self.index += 1
        self._show_current()

    def run(self) -> None:
        self.root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review similar photo pairs and mark which one to keep."
    )
    parser.add_argument(
        "--pairs",
        required=True,
        help="CSV from similarity_scan.py (pairs_for_review.csv).",
    )
    parser.add_argument(
        "--log",
        default="review_log.csv",
        help="Output CSV to append decisions.",
    )
    parser.add_argument(
        "--filter-type",
        choices=["cross_library", "photos_dupe"],
        help="Review only a specific pair type.",
    )
    parser.add_argument(
        "--start-at",
        type=int,
        default=1,
        help="Start from this pair_id (useful for resuming).",
    )
    parser.add_argument(
        "--max-size",
        type=int,
        default=1600,
        help="Max image size (pixels) when displaying.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    pairs = _load_pairs(Path(args.pairs), filter_type=args.filter_type)
    existing = _load_existing(Path(args.log))

    pending = [p for p in pairs if p["pair_id"] >= args.start_at and p["pair_id"] not in existing]
    if not pending:
        print("No pending pairs to review.")
        return

    reviewer = PairReviewer(
        pairs=pending,
        log_path=Path(args.log),
        start_index=0,
        max_size=args.max_size,
    )
    reviewer.run()


if __name__ == "__main__":
    main()
