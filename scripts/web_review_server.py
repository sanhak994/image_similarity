from __future__ import annotations

import csv
import hashlib
import os
import threading
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, jsonify, request, send_file, send_from_directory, abort
from PIL import Image

# allow large images
Image.MAX_IMAGE_PIXELS = None


BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = BASE_DIR.parent / "work"
PAIRS_PATH = WORK_DIR / "pairs_for_review.csv"
LOG_PATH = WORK_DIR / "review_log.csv"
STATIC_DIR = BASE_DIR / "static"
IMAGE_CACHE = WORK_DIR / ".cache_images"
IMAGE_CACHE.mkdir(parents=True, exist_ok=True)
RAW_EXTS = {".nef", ".cr2", ".cr3", ".arw", ".raf", ".orf", ".rw2", ".dng"}


DECISION_KEEP_LEFT = "keep_left"
DECISION_KEEP_RIGHT = "keep_right"
DECISION_KEEP_BOTH = "keep_both"
DECISION_SKIP = "skip"
DECISION_DELETE_BOTH = "delete_both"
DECISION_KEEP_PRIMARY = "keep_primary"


@dataclass
class PhotoSide:
    library: str
    uuid: str
    path: str
    filename: str
    url: str


@dataclass
class PairRecord:
    pair_id: int
    pair_type: str
    distance: int
    hash_method: str
    hash_bits: int
    left: PhotoSide
    right: PhotoSide
    decision: Optional[str] = None
    delete_uuid: str | None = None
    delete_library: str | None = None
    keep_uuid: str | None = None
    keep_library: str | None = None

    def to_dict(self) -> dict:
        left_exists = os.path.isfile(self.left.path)
        right_exists = os.path.isfile(self.right.path)
        return {
            "pair_id": self.pair_id,
            "pair_type": self.pair_type,
            "distance": self.distance,
            "hash_method": self.hash_method,
            "hash_bits": self.hash_bits,
            "left": {
                "library": self.left.library,
                "uuid": self.left.uuid,
                "filename": self.left.filename,
                "url": self.left.url,
                "path": self.left.path,
                "exists": left_exists,
            },
            "right": {
                "library": self.right.library,
                "uuid": self.right.uuid,
                "filename": self.right.filename,
                "url": self.right.url,
                "path": self.right.path,
                "exists": right_exists,
            },
            "decision": self.decision,
            "delete_uuid": self.delete_uuid,
            "delete_library": self.delete_library,
            "keep_uuid": self.keep_uuid,
            "keep_library": self.keep_library,
        }


def _hash_path(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def _convert_image(path: str) -> Optional[Path]:
    """Convert non-browser-friendly formats to jpeg and cache."""
    src = Path(path)
    cache_name = _hash_path(path) + ".jpg"
    cache_path = IMAGE_CACHE / cache_name

    if cache_path.exists():
        return cache_path

    try:
        with Image.open(src) as img:
            img = img.convert("RGB")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(cache_path, format="JPEG", quality=92)
            return cache_path
    except Exception as e:
        # Fallback to sips conversion for RAW formats
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["sips", "-s", "format", "jpeg", str(src), "--out", str(cache_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and cache_path.exists():
                return cache_path
            else:
                print(f"sips failed on {src}: {result.stderr}")
        except Exception as exc:
            print(f"RAW convert failed for {src}: {exc}")
        return None


class PairStore:
    def __init__(self, pairs_path: Path, log_path: Path, primary_library: str = "photos"):
        self.pairs_path = pairs_path
        self.log_path = log_path
        self.lock = threading.Lock()
        self.primary_library = primary_library
        self.image_map: Dict[str, str] = {}  # id -> absolute path
        self.pairs: Dict[int, PairRecord] = {}
        self._load_pairs()
        self._load_log()

    def _load_pairs(self) -> None:
        if not self.pairs_path.exists():
            self.pairs = {}
            return

        with self.pairs_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                pair_id = int(row["pair_id"])
                dist = int(row["distance"])
                left_path = os.path.abspath(row["path_left"])
                right_path = os.path.abspath(row["path_right"])
                left_id = _hash_path(left_path + str(pair_id) + "L")
                right_id = _hash_path(right_path + str(pair_id) + "R")
                self.image_map[left_id] = left_path
                self.image_map[right_id] = right_path

                left = PhotoSide(
                    library=row["library_left"],
                    uuid=row["uuid_left"],
                    path=left_path,
                    filename=row["filename_left"],
                    url=f"/image/{left_id}",
                )
                right = PhotoSide(
                    library=row["library_right"],
                    uuid=row["uuid_right"],
                    path=right_path,
                    filename=row["filename_right"],
                    url=f"/image/{right_id}",
                )

                record = PairRecord(
                    pair_id=pair_id,
                    pair_type=row["pair_type"],
                    distance=dist,
                    hash_method=row.get("hash_method", ""),
                    hash_bits=int(row.get("hash_bits", "0") or 0),
                    left=left,
                    right=right,
                )
                self.pairs[pair_id] = record

        self.pairs = dict(sorted(self.pairs.items(), key=lambda kv: kv[0]))

    def _load_log(self) -> None:
        if not self.log_path.exists():
            return
        with self.log_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                pair_id = int(row["pair_id"])
                if pair_id not in self.pairs:
                    continue
                rec = self.pairs[pair_id]
                rec.decision = row.get("decision") or None
                rec.delete_uuid = row.get("delete_uuid") or None
                rec.delete_library = row.get("delete_library") or None
                rec.keep_uuid = row.get("keep_uuid") or None
                rec.keep_library = row.get("keep_library") or None

    def _decision_payload(self, rec: PairRecord, decision: str) -> dict:
        delete_uuid_other = ""
        delete_library_other = ""

        if decision == DECISION_KEEP_LEFT:
            delete_uuid = rec.right.uuid
            delete_library = rec.right.library
            keep_uuid = rec.left.uuid
            keep_library = rec.left.library
        elif decision == DECISION_KEEP_RIGHT:
            delete_uuid = rec.left.uuid
            delete_library = rec.left.library
            keep_uuid = rec.right.uuid
            keep_library = rec.right.library
        elif decision == DECISION_DELETE_BOTH:
            delete_uuid = rec.left.uuid
            delete_library = rec.left.library
            delete_uuid_other = rec.right.uuid
            delete_library_other = rec.right.library
            keep_uuid = ""
            keep_library = ""
        elif decision == DECISION_KEEP_PRIMARY:
            if rec.left.library == self.primary_library:
                delete_uuid = rec.right.uuid
                delete_library = rec.right.library
                keep_uuid = rec.left.uuid
                keep_library = rec.left.library
            elif rec.right.library == self.primary_library:
                delete_uuid = rec.left.uuid
                delete_library = rec.left.library
                keep_uuid = rec.right.uuid
                keep_library = rec.right.library
            else:
                delete_uuid = ""
                delete_library = ""
                keep_uuid = ""
                keep_library = ""
        elif decision == DECISION_KEEP_BOTH:
            delete_uuid = ""
            delete_library = ""
            keep_uuid = ""
            keep_library = ""
        else:  # skip or unknown
            delete_uuid = ""
            delete_library = ""
            keep_uuid = ""
            keep_library = ""

        return {
            "pair_id": rec.pair_id,
            "pair_type": rec.pair_type,
            "decision": decision,
            "distance": rec.distance,
            "delete_uuid": delete_uuid,
            "delete_library": delete_library,
            "delete_uuid_other": delete_uuid_other,
            "delete_library_other": delete_library_other,
            "keep_uuid": keep_uuid,
            "keep_library": keep_library,
            "uuid_left": rec.left.uuid,
            "uuid_right": rec.right.uuid,
            "path_left": rec.left.path,
            "path_right": rec.right.path,
        }

    def write_log(self) -> None:
        fieldnames = [
            "pair_id",
            "pair_type",
            "decision",
            "distance",
            "delete_uuid",
            "delete_library",
            "delete_uuid_other",
            "delete_library_other",
            "keep_uuid",
            "keep_library",
            "uuid_left",
            "uuid_right",
            "path_left",
            "path_right",
        ]
        rows: List[dict] = []
        for rec in self.pairs.values():
            if not rec.decision:
                continue
            rows.append(self._decision_payload(rec, rec.decision))

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def set_decision(self, pair_id: int, decision: str) -> PairRecord:
        if pair_id not in self.pairs:
            raise KeyError(f"Unknown pair_id {pair_id}")
        rec = self.pairs[pair_id]
        rec.decision = decision
        payload = self._decision_payload(rec, decision)
        rec.delete_uuid = payload["delete_uuid"] or None
        rec.delete_library = payload["delete_library"] or None
        # other side deletion stored in log only
        rec.keep_uuid = payload["keep_uuid"] or None
        rec.keep_library = payload["keep_library"] or None

        with self.lock:
            self.write_log()
        return rec

    def as_list(self) -> List[dict]:
        return [rec.to_dict() for rec in self.pairs.values()]

    def get_image_path(self, image_id: str) -> Optional[str]:
        return self.image_map.get(image_id)

    def stats(self) -> dict:
        total = len(self.pairs)
        decided = sum(1 for p in self.pairs.values() if p.decision)
        return {
            "total": total,
            "decided": decided,
            "pending": total - decided,
            "primary_library": self.primary_library,
        }

    def apply_batch_keep_primary(self) -> dict:
        count = 0
        for rec in self.pairs.values():
            if rec.pair_type != "cross_library":
                continue
            if rec.left.library != self.primary_library and rec.right.library != self.primary_library:
                continue
            rec.decision = DECISION_KEEP_PRIMARY
            payload = self._decision_payload(rec, DECISION_KEEP_PRIMARY)
            rec.delete_uuid = payload["delete_uuid"] or None
            rec.delete_library = payload["delete_library"] or None
            rec.keep_uuid = payload["keep_uuid"] or None
            rec.keep_library = payload["keep_library"] or None
            count += 1
        with self.lock:
            self.write_log()
        return {"updated": count}

    def clear_batch_keep_primary(self) -> dict:
        """Clear keep_primary decisions for cross-library pairs set to keep_primary."""
        count = 0
        for rec in self.pairs.values():
            if rec.pair_type != "cross_library":
                continue
            if rec.decision != DECISION_KEEP_PRIMARY:
                continue
            rec.decision = None
            rec.delete_uuid = None
            rec.delete_library = None
            rec.keep_uuid = None
            rec.keep_library = None
            count += 1
        with self.lock:
            self.write_log()
        return {"cleared": count}


def run_subprocess_async(cmd: List[str], workdir: Path) -> Dict[str, str]:
    task_id = hashlib.sha256(" ".join(cmd).encode()).hexdigest()[:10]
    TASKS[task_id] = {"status": "running", "cmd": cmd, "output": "", "error": ""}

    def _run():
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            ACTIVE_PROCS[task_id] = proc
            output_lines = []
            for line in proc.stdout:
                output_lines.append(line)
                TASKS[task_id]["output"] = "".join(output_lines)
            proc.wait()
            TASKS[task_id]["status"] = "finished" if proc.returncode == 0 else "failed"
            ACTIVE_PROCS.pop(task_id, None)
        except Exception as exc:
            TASKS[task_id]["status"] = "failed"
            TASKS[task_id]["error"] = str(exc)
            ACTIVE_PROCS.pop(task_id, None)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {"task_id": task_id}


app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
TASKS: Dict[str, Dict] = {}
ACTIVE_PROCS: Dict[str, subprocess.Popen] = {}
store = PairStore(PAIRS_PATH, LOG_PATH)


@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/api/pairs")
def api_pairs():
    return jsonify({"pairs": store.as_list(), "stats": store.stats()})


@app.route("/api/decision", methods=["POST"])
def api_decision():
    data = request.get_json(force=True)
    pair_id = data.get("pair_id")
    decision = data.get("decision")
    if pair_id is None or decision not in {
        DECISION_KEEP_LEFT,
        DECISION_KEEP_RIGHT,
        DECISION_KEEP_BOTH,
        DECISION_SKIP,
        DECISION_DELETE_BOTH,
        DECISION_KEEP_PRIMARY,
    }:
        return jsonify({"error": "Invalid payload"}), 400
    try:
        rec = store.set_decision(int(pair_id), decision)
    except KeyError:
        return jsonify({"error": "Unknown pair_id"}), 404
    return jsonify({"pair": rec.to_dict(), "stats": store.stats()})


@app.route("/image/<image_id>")
def image(image_id: str):
    path = store.get_image_path(image_id)
    if not path:
        app.logger.warning("Image id %s not found in map", image_id)
        abort(404)
    if not os.path.isfile(path):
        app.logger.warning("Image missing on disk: %s", path)
        abort(404)
    ext = Path(path).suffix.lower()
    if ext in RAW_EXTS:
        converted = _convert_image(path)
        if converted and converted.exists():
            return send_file(converted)
        app.logger.warning("Failed to convert raw image: %s", path)
        # fall through to attempt to serve original (may fail)
    return send_file(path)


@app.route("/api/stats")
def api_stats():
    return jsonify(store.stats())


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "GET":
        return jsonify({"primary_library": store.primary_library})
    data = request.get_json(force=True)
    primary = data.get("primary_library")
    if primary not in {"photos", "iphoto"}:
        return jsonify({"error": "primary_library must be 'photos' or 'iphoto'"}), 400
    store.primary_library = primary
    return jsonify({"primary_library": store.primary_library})


@app.route("/api/batch/keep_primary", methods=["POST"])
def api_batch_keep_primary():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "apply")
    if action == "clear":
        result = store.clear_batch_keep_primary()
    else:
        result = store.apply_batch_keep_primary()
    return jsonify({"result": result, "stats": store.stats()})


@app.route("/api/task/start", methods=["POST"])
def api_task_start():
    data = request.get_json(force=True)
    task = data.get("task")
    params = data.get("params", {})
    if task not in {"scan", "album", "export_missing", "export_keepers"}:
        return jsonify({"error": "Invalid task"}), 400

    cmd = [sys.executable]
    if task == "scan":
        photos_lib = params.get("photos_lib", "").strip()
        if not photos_lib:
            return jsonify({"error": "photos_lib is required"}), 400
        cmd += [
            str(BASE_DIR / "similarity_scan.py"),
            "--photos-lib",
            photos_lib,
        ]
        iphoto = params.get("iphoto_lib", "")
        if iphoto:
            cmd += ["--iphoto-lib", iphoto]
        if params.get("prefer_edited"):
            cmd.append("--prefer-edited")
        cmd += [
            "--hash-method",
            params.get("hash_method", "phash"),
            "--hash-size",
            str(params.get("hash_size", 16)),
            "--threshold-dupes",
            str(params.get("threshold_dupes", 5)),
            "--threshold-cross",
            str(params.get("threshold_cross", 8)),
            "--workers",
            str(params.get("workers", 4)),
        ]
    elif task == "album":
        cmd += [
            str(BASE_DIR / "create_deletion_album.py"),
            "--log",
            str(LOG_PATH),
        ]
        album_name = params.get("album_name")
        if album_name:
            cmd += ["--album-name", album_name]
        if params.get("dry_run"):
            cmd.append("--dry-run")
    elif task == "export_missing":
        src = params.get("source_lib", "").strip()
        other = params.get("other_lib", "").strip()
        dest = params.get("dest", "").strip()
        if not (src and other and dest):
            return jsonify({"error": "source_lib, other_lib, and dest are required"}), 400
        cmd += [
            str(BASE_DIR / "export_ops.py"),
            "--mode",
            "missing",
            "--source",
            src,
            "--other",
            other,
            "--dest",
            dest,
        ]
    elif task == "export_keepers":
        src = params.get("source_lib", "").strip()
        dest = params.get("dest", "").strip()
        if not (src and dest):
            return jsonify({"error": "source_lib and dest are required"}), 400
        cmd += [
            str(BASE_DIR / "export_ops.py"),
            "--mode",
            "keepers",
            "--source",
            src,
            "--dest",
            dest,
            "--log",
            str(LOG_PATH),
        ]

    app.logger.info("Starting task %s: %s", task, cmd)
    task_info = run_subprocess_async(cmd, BASE_DIR.parent)
    return jsonify(task_info)


@app.route("/api/task/status")
def api_task_status():
    task_id = request.args.get("task_id")
    if not task_id or task_id not in TASKS:
        return jsonify({"error": "unknown task"}), 404
    return jsonify(TASKS[task_id])


@app.route("/api/task/stop", methods=["POST"])
def api_task_stop():
    data = request.get_json(force=True)
    task_id = data.get("task_id")
    proc = ACTIVE_PROCS.get(task_id)
    if not proc:
        return jsonify({"error": "unknown or finished task"}), 404
    proc.terminate()
    TASKS[task_id]["status"] = "stopped"
    return jsonify({"status": "stopped", "task_id": task_id})


if __name__ == "__main__":
    print("Serving review UI at http://localhost:7001")
    app.run(host="0.0.0.0", port=7001, debug=False)
