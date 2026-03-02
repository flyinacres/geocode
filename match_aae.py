#!/usr/bin/env python3
"""
Match AAE sidecar files in unknown/ folders to their corresponding
image files and move them to the same location folder.

AAE files are named identically to their image (e.g. IMG_1234.AAE
matches IMG_1234.JPG or IMG_1234.HEIC).

Usage: python3 match_aae.py /path/to/organized
"""

import os
import sys
import shutil

ORGANIZED_DIR = sys.argv[1] if len(sys.argv) > 1 else "./organized"

# Build a map of all image filenames (without extension) to their full path
print("Building index of all image files...")
image_index = {}
for root, dirs, files in os.walk(ORGANIZED_DIR):
    # Skip unknown folders when building the index
    if os.path.basename(root) == "unknown":
        continue
    for filename in files:
        if filename.startswith('.'):
            continue
        stem = os.path.splitext(filename)[0]
        image_index[stem] = root

matched = 0
unmatched = 0

# Find all AAE files in unknown folders
for root, dirs, files in os.walk(ORGANIZED_DIR):
    if os.path.basename(root) != "unknown":
        continue
    for filename in files:
        ext = os.path.splitext(filename)[1].lower()
        if ext != ".aae":
            continue
        stem = os.path.splitext(filename)[0]
        filepath = os.path.join(root, filename)

        if stem in image_index:
            dest_dir = image_index[stem]
            dest_path = os.path.join(dest_dir, filename)
            if os.path.exists(dest_path):
                print(f"  WARNING: {filename} already exists at destination, skipping")
                continue
            print(f"  {filename} -> {os.path.relpath(dest_dir, ORGANIZED_DIR)}/")
            shutil.move(filepath, dest_path)
            matched += 1
        else:
            print(f"  No match found for {filename}, leaving in unknown/")
            unmatched += 1

print(f"\nDone. Matched: {matched}, No match found: {unmatched}")