#!/usr/bin/env python3
"""
Move files from unknown/ folders to a location folder based on
timestamps of nearby geocoded photos.

For each unknown file, finds all geocoded photos in the same month
taken within WINDOW_MINUTES and assigns the most common location.
Files with no neighbors within the window stay in unknown/.

Usage: python3 match_by_time.py /path/to/organized [window_minutes]
Default window is 30 minutes.
"""

import os
import sys
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from collections import Counter

ORGANIZED_DIR = sys.argv[1] if len(sys.argv) > 1 else "./organized"
WINDOW_MINUTES = int(sys.argv[2]) if len(sys.argv) > 2 else 30

def get_datetime(filepath):
    """Extract DateTimeOriginal or CreateDate as a datetime object."""
    result = subprocess.run(
        ["exiftool", "-j", "-DateTimeOriginal", "-CreateDate", "-SubSecDateTimeOriginal", filepath],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)[0]
        for field in ["SubSecDateTimeOriginal", "DateTimeOriginal", "CreateDate"]:
            val = data.get(field)
            if val:
                # Strip subseconds and timezone for parsing
                val = val[:19].replace(":", "-", 2)
                return datetime.fromisoformat(val)
    except (json.JSONDecodeError, IndexError, KeyError, ValueError):
        pass
    return None

def move_file(filepath, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, os.path.basename(filepath))
    if os.path.exists(dest_path):
        print(f"  WARNING: {os.path.basename(filepath)} already exists, skipping")
        return False
    shutil.move(filepath, dest_path)
    return True

moved = 0
stayed = 0

for year in sorted(os.listdir(ORGANIZED_DIR)):
    year_path = os.path.join(ORGANIZED_DIR, year)
    if not os.path.isdir(year_path) or not year.isdigit():
        continue

    for month in sorted(os.listdir(year_path)):
        month_path = os.path.join(year_path, month)
        if not os.path.isdir(month_path):
            continue

        # Process both unknown/ and Unknown/ as sources
        unknown_dirs = [
            os.path.join(month_path, "unknown"),
            os.path.join(month_path, "Unknown"),
        ]
        unknown_dirs = [d for d in unknown_dirs if os.path.isdir(d)]
        if not unknown_dirs:
            continue

        print(f"\nProcessing {year}/{month}/unknown...")

        # Build index of geocoded files: {datetime: location_folder_name}
        geocoded = {}
        for location in os.listdir(month_path):
            if location.lower() == "unknown":
                continue
            loc_path = os.path.join(month_path, location)
            if not os.path.isdir(loc_path):
                continue
            for filename in os.listdir(loc_path):
                if filename.startswith('.'):
                    continue
                filepath = os.path.join(loc_path, filename)
                dt = get_datetime(filepath)
                if dt:
                    geocoded[dt] = location

        if not geocoded:
            print(f"  No geocoded files in this month, skipping")
            continue

        geocoded_times = sorted(geocoded.keys())

        # Process each unknown file
        for unknown_dir in unknown_dirs:
          for filename in os.listdir(unknown_dir):
            if filename.startswith('.'):
                continue
            filepath = os.path.join(unknown_dir, filename)
            dt = get_datetime(filepath)

            if not dt:
                stayed += 1
                continue

            # Find all geocoded files within the time window
            window = timedelta(minutes=WINDOW_MINUTES)
            nearby = [geocoded[t] for t in geocoded_times
                      if abs(t - dt) <= window]

            if nearby:
                # Use most common location among neighbors
                location = Counter(nearby).most_common(1)[0][0]
                dest_dir = os.path.join(month_path, location)
                print(f"  {filename} -> {location}/")
                if move_file(filepath, dest_dir):
                    moved += 1
            else:
                stayed += 1

print(f"\nDone. Moved: {moved}, Still unknown: {stayed}")