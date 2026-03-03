#!/usr/bin/env python3
"""
Sort iPhone photos into YYYY/MM folder structure by date.

Handles all file types produced by iPhone:
  JPG, JPEG, HEIC, PNG, WEBP  -- uses DateTimeOriginal
  MOV, MP4                    -- uses CreationDate then CreateDate
  AAE                         -- paired with matching image by filename,
                                 falls back to FileModifyDate

Files without any date metadata go into YYYY/MM based on FileModifyDate.
AAE files are moved alongside their paired image file wherever that lands.

Copies files rather than moving -- verify results before deleting source.
Everything is logged to sort.log in the destination directory.

Usage:
    python3 sort_photos.py <source_dir> <dest_dir>

Example:
    python3 sort_photos.py "/Volumes/iPhone/DCIM" "/Pictures/organized"
"""

import os
import sys
import json
import shutil
import logging
import subprocess
from datetime import datetime
from collections import defaultdict

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SOURCE_DIR = sys.argv[1] if len(sys.argv) > 1 else "./source"
DEST_DIR   = sys.argv[2] if len(sys.argv) > 2 else "./organized"

# Map file extensions to the exiftool date fields to try, in order
DATE_FIELDS = {
    ".jpg":  ["DateTimeOriginal", "CreateDate", "FileModifyDate"],
    ".jpeg": ["DateTimeOriginal", "CreateDate", "FileModifyDate"],
    ".heic": ["DateTimeOriginal", "CreateDate", "FileModifyDate"],
    ".png":  ["DateTimeOriginal", "CreateDate", "FileModifyDate"],
    ".webp": ["DateTimeOriginal", "CreateDate", "FileModifyDate"],
    ".mov":  ["CreationDate",     "CreateDate", "FileModifyDate"],
    ".mp4":  ["CreationDate",     "CreateDate", "FileModifyDate"],
    ".aae":  ["FileModifyDate"],  # AAE files have no camera date; handled separately
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

os.makedirs(DEST_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(DEST_DIR, "sort.log")),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_date(filepath):
    """
    Extract the best available date from a file using exiftool.
    Tries each field in order for the file's extension.
    Returns a (year, month) tuple of strings, e.g. ("2024", "06").
    """
    ext = os.path.splitext(filepath)[1].lower()
    fields = DATE_FIELDS.get(ext, ["DateTimeOriginal", "CreateDate", "FileModifyDate"])

    # Build exiftool command requesting all relevant fields at once
    tag_args = [f"-{f}" for f in fields]
    result = subprocess.run(
        ["exiftool", "-j"] + tag_args + [filepath],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)[0]
        for field in fields:
            val = data.get(field)
            if val:
                # Dates come in formats like "2024:06:14 19:50:20" or with timezone
                # Take first 7 chars after stripping to get "2024:06"
                clean = val.strip()[:7]
                parts = clean.replace("-", ":").split(":")
                if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                    return (parts[0], parts[1].zfill(2))
    except (json.JSONDecodeError, IndexError, KeyError):
        pass

    log.warning(f"No date found for {filepath}")
    return None

def dest_path_for(filepath, year, month):
    """Build the destination path for a file."""
    filename = os.path.basename(filepath)
    return os.path.join(DEST_DIR, year, month, filename)

def safe_copy(src, dst):
    """
    Copy src to dst. Creates parent directories as needed.
    If a file with the same name already exists at dst, skips and logs a warning.
    Returns True if copied, False if skipped.
    """
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        log.warning(f"SKIP (exists): {dst}")
        return False
    shutil.copy2(src, dst)
    return True

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info(f"Source:      {SOURCE_DIR}")
    log.info(f"Destination: {DEST_DIR}")

    # Collect all files first so we can pair AAE files with their images
    all_files = []
    for root, dirs, files in os.walk(SOURCE_DIR):
        for filename in files:
            if not filename.startswith('.'):
                all_files.append(os.path.join(root, filename))

    log.info(f"Found {len(all_files)} files to process")

    # First pass: sort all non-AAE files and record where they landed
    # image_destinations maps filename stem -> (year, month)
    image_destinations = {}
    copied = 0
    skipped = 0
    no_date = 0

    for filepath in all_files:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".aae":
            continue

        stem = os.path.splitext(os.path.basename(filepath))[0]
        date = get_date(filepath)

        if date:
            year, month = date
        else:
            # Should be rare -- log it and use a fallback folder
            log.warning(f"No date for {filepath}, placing in 0000/00")
            year, month = "0000", "00"
            no_date += 1

        dst = dest_path_for(filepath, year, month)
        if safe_copy(filepath, dst):
            image_destinations[stem] = (year, month)
            copied += 1
        else:
            skipped += 1

    log.info(f"Images: {copied} copied, {skipped} skipped, {no_date} had no date")

    # Second pass: move AAE files alongside their paired image
    aae_files = [f for f in all_files if os.path.splitext(f)[1].lower() == ".aae"]
    aae_matched = 0
    aae_fallback = 0
    aae_skipped = 0

    for filepath in aae_files:
        stem = os.path.splitext(os.path.basename(filepath))[0]

        if stem in image_destinations:
            # Pair with the image that was already sorted
            year, month = image_destinations[stem]
            aae_matched += 1
        else:
            # No matching image found -- fall back to file date
            date = get_date(filepath)
            if date:
                year, month = date
            else:
                year, month = "0000", "00"
            aae_fallback += 1
            log.warning(f"No image match for AAE: {os.path.basename(filepath)}, using date fallback")

        dst = dest_path_for(filepath, year, month)
        if safe_copy(filepath, dst):
            pass
        else:
            aae_skipped += 1

    log.info(f"AAE files: {aae_matched} paired, {aae_fallback} date fallback, {aae_skipped} skipped")
    log.info("Sort complete. Verify destination before deleting source.")

if __name__ == "__main__":
    main()