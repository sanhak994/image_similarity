## Photo similarity toolkit

Workflow to compare an iPhoto library against a Photos library, review similar pairs, and flag Photos items for deletion.

### Prereqs
- Use the existing virtualenv: `source venv_photos/bin/activate`
- Install viewers/hash deps (osxphotos already installed): `pip install pillow ImageHash`
- Paths (update if needed):
  - Photos: `/Volumes/Storage/photos_lib_workin_dir.photoslibrary`
  - iPhoto: `/Volumes/Storage/iphoto_working_dir.photolibrary`

### 1) Generate similarity candidates
```
python scripts/similarity_scan.py \
  --photos-lib "/Volumes/Storage/photos_lib_workin_dir.photoslibrary" \
  --iphoto-lib "/Volumes/Storage/iphoto_working_dir.photolibrary" \
  --hash-method phash --hash-size 16 \
  --threshold-dupes 5 --threshold-cross 8 \
  --workers 4
```
- Outputs (always under `work/`): `pairs_for_review.csv`, `photos_hashes.json`, `iphoto_hashes.json`, `unique_in_iphoto.csv` (if anything only in iPhoto), `hash_errors.log`.
- No exporting occurs; PhotosDB must be supported (works with macOS 15 and osxphotos 0.74.1+).
- Tuning: lower thresholds catch only near-identical photos; higher thresholds find looser matches. Use `--prefer-edited` to hash edited versions first.

### 2) Review pairs (side-by-side)
Start the web reviewer (uses Flask) and open http://localhost:5000:
```
source venv310/bin/activate
pip install -r requirements.txt
python scripts/web_review_server.py
```
- Keyboard: `L` keep left, `R` keep right, `B` keep both, `N/S` skip/next, `P`/Left Arrow back, Right Arrow forward.
- Decisions save immediately to `work/review_log.csv` (same format as before).

### 3) Create a Photos album of items to delete
```
python scripts/create_deletion_album.py \
  --log work/review_log.csv \
  --album-name "To Delete (reviewed)"
```
- Adds Photos-library items marked as the “delete” side to the album (default name `To Delete YYYY-MM-DD`). Use `--dry-run` to preview.

### Notes
- Similarity uses perceptual hashes (phash/ahash/dhash/whash) with adjustable size and Hamming thresholds.
- Images missing from disk/iCloud are skipped and noted in `hash_errors.log`.
- Scripts do not alter libraries directly; only the final step writes to Photos by adding an album. Allow Photos automation when prompted.
- This repo wasn’t able to run Photos automation in the sandbox, so please run commands locally in your macOS user session.
