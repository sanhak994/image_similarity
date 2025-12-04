# Repository Guidelines

## Project Structure & Module Organization
- `scripts/`: standalone tools for hashing libraries, building pair lists, reviewing pairs, and creating deletion albums (`similarity_scan.py`, `review_pairs.py`, `photo_library.py`, `hash_utils.py`, `bktree.py`, `create_deletion_album.py`).
- `README.md`: quickstart workflow and command examples.
- `venv_photos/`: local virtualenv (ignored in git); use for dependencies (`osxphotos`, `pillow`, `ImageHash`).

## Build, Test, and Development Commands
- Activate env: `source venv_photos/bin/activate`.
- Install extras: `pip install pillow ImageHash`.
- Generate pairs: `python scripts/similarity_scan.py --photos-lib <path> --iphoto-lib <path> --output-dir work`.
- Review pairs: `python scripts/review_pairs.py --pairs work/pairs_for_review.csv --log work/review_log.csv`.
- Create deletion album: `python scripts/create_deletion_album.py --log work/review_log.csv --album-name "To Delete"`.
- No formal build/test pipeline; run scripts directly.

## Coding Style & Naming Conventions
- Language: Python 3.9+. Prefer small, single-purpose modules (no monoliths).
- Style: 4-space indent, type hints, concise comments only where logic is non-obvious.
- Strings/paths: use `Path` from `pathlib` when practical; avoid hardcoding user-specific paths.
- Hashing/display dependencies: guard imports where GUI/image libs may be missing; provide actionable error text.

## Testing Guidelines
- No test suite present. When adding functionality, prefer small, script-level sanity checks (e.g., dry-runs, temp output dirs).
- If adding tests, colocate under `tests/` using `pytest`; name files `test_*.py`.

## Commit & Pull Request Guidelines
- Commit messages: present tense, concise subject (e.g., `Add pair reviewer UI guard`); batch related changes logically.
- PRs should describe scope, usage changes, and any new flags; include reproduction/usage commands (paths, thresholds) and note sandbox/Photos.app constraints.
- Do not commit `venv_photos/`, local outputs (`work/`, logs, CSVs), or OS-generated files.

## Agent-Specific Tips
- Photos/AppleScript calls require a real macOS session; expect automation prompts.
- Hashing large libraries is I/O bound—allow CLI flags (`--workers`, thresholds) to stay responsive and reproducible.
