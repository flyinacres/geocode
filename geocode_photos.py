#!/usr/bin/env python3
"""
Organize photos within each YYYY/MM folder into location subfolders.

Algorithm:
  1. Read timestamps of all files in a month folder
  2. Cluster files by time gap -- a new cluster starts when consecutive
     photos are more than CLUSTER_GAP_MINUTES apart
  3. For each cluster, collect GPS coordinates from files that have them
  4. Geocode the dominant GPS location for the cluster
  5. Name the subfolder after that location (e.g. "Bangkok-TH")
     If no GPS exists in the cluster, name by date range (e.g. "06-14_to_06-18")
  6. Move all files in the cluster to that subfolder -- GPS or not

This means nothing is ever orphaned. Location is just a label on a
time-based group.

GPS cache is saved to disk so interrupted runs don't re-query Nominatim.

Usage:
    python3 geocode_photos.py <organized_dir> [cluster_gap_minutes]

Example:
    python3 geocode_photos.py "/Pictures/organized" 60

Requirements:
    pip install geopy
"""

import os
import sys
import json
import time
import shutil
import logging
import subprocess
from datetime import datetime, timedelta
from collections import Counter

try:
    from geopy.geocoders import Nominatim
except ImportError:
    print("ERROR: geopy not installed. Run: pip install geopy")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ORGANIZED_DIR       = sys.argv[1] if len(sys.argv) > 1 else "./organized"
CLUSTER_GAP_MINUTES = int(sys.argv[2]) if len(sys.argv) > 2 else 60

# Nominatim rate limit -- do not reduce below 1.0
NOMINATIM_DELAY = 1.1

# Coordinate rounding precision -- 3 decimal places is ~100m
# Reduces redundant API calls for photos taken in the same area
COORD_PRECISION = 3

# Cache file -- saves geocoding results to disk so reruns don't re-query
CACHE_FILE = os.path.join(ORGANIZED_DIR, ".geocode_cache.json")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(ORGANIZED_DIR, "geocode.log")),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GPS cache (persisted to disk)
# ---------------------------------------------------------------------------

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except IOError as e:
        log.warning(f"Could not save cache: {e}")

geo_cache = load_cache()
geolocator = Nominatim(user_agent="photo_organizer_v2")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_datetime(filepath):
    """
    Extract the best available timestamp from a file.
    Returns a datetime object or None.
    Tries DateTimeOriginal, CreationDate, CreateDate, FileModifyDate in order.
    """
    result = subprocess.run(
        ["exiftool", "-j",
         "-DateTimeOriginal", "-CreationDate", "-CreateDate", "-FileModifyDate",
         filepath],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)[0]
        for field in ["DateTimeOriginal", "CreationDate", "CreateDate", "FileModifyDate"]:
            val = data.get(field)
            if val:
                # Strip subseconds and timezone, normalize separators
                clean = val.strip()[:19].replace(":", "-", 2)
                try:
                    return datetime.fromisoformat(clean)
                except ValueError:
                    continue
    except (json.JSONDecodeError, IndexError, KeyError):
        pass
    return None

def get_gps(filepath):
    """
    Extract GPS coordinates as floats using # suffix for numeric output.
    Returns (lat, lon) tuple or None.
    """
    result = subprocess.run(
        ["exiftool", "-j", "-GPSLatitude#", "-GPSLongitude#", filepath],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)[0]
        lat = data.get("GPSLatitude")
        lon = data.get("GPSLongitude")
        if lat is not None and lon is not None:
            return (float(lat), float(lon))
    except (json.JSONDecodeError, IndexError, KeyError, ValueError):
        pass
    return None

def round_coords(coords):
    return (round(coords[0], COORD_PRECISION), round(coords[1], COORD_PRECISION))

def geocode(coords):
    """
    Reverse geocode coordinates to a location name like "Auburn-US".
    Uses progressive fallback through address fields.
    Results are cached to disk.
    Returns a string or None if no place name can be found.
    """
    key = str(round_coords(coords))
    if key in geo_cache:
        return geo_cache[key]

    try:
        loc = geolocator.reverse(coords, language="en", zoom=14)
        time.sleep(NOMINATIM_DELAY)
        if loc:
            addr = loc.raw.get("address", {})
            country = addr.get("country_code", "").upper()
            place = (
                addr.get("city") or
                addr.get("town") or
                addr.get("village") or
                addr.get("suburb") or
                addr.get("neighbourhood") or
                addr.get("hamlet") or
                addr.get("county") or
                addr.get("state_district") or
                addr.get("state") or
                country or
                None
            )
            if place:
                name = f"{place}-{country}" if country and place != country else place
                geo_cache[key] = name
                save_cache(geo_cache)
                return name
    except Exception as e:
        log.warning(f"Geocoding error for {coords}: {e}")
        time.sleep(NOMINATIM_DELAY)

    geo_cache[key] = None
    save_cache(geo_cache)
    return None

def cluster_by_time(file_times, gap_minutes):
    """
    Group files into clusters based on time gaps.
    A new cluster starts when consecutive files are more than gap_minutes apart.

    file_times: list of (filepath, datetime) sorted by datetime
    Returns: list of lists of filepaths
    """
    if not file_times:
        return []

    clusters = []
    current = [file_times[0][0]]
    gap = timedelta(minutes=gap_minutes)

    for i in range(1, len(file_times)):
        prev_dt = file_times[i-1][1]
        curr_dt = file_times[i][1]
        if curr_dt - prev_dt > gap:
            clusters.append(current)
            current = []
        current.append(file_times[i][0])

    clusters.append(current)
    return clusters

def name_for_cluster(filepaths, month_dir):
    """
    Determine the folder name for a cluster of files.
    Geocodes GPS coordinates if available.
    Falls back to date range if no GPS found.
    """
    # Collect GPS from all files in cluster
    locations = []
    for fp in filepaths:
        coords = get_gps(fp)
        if coords:
            name = geocode(coords)
            if name:
                locations.append(name)

    if locations:
        # Use most common location in the cluster
        return Counter(locations).most_common(1)[0][0]

    # No GPS -- name by date range of the cluster
    dates = []
    for fp in filepaths:
        dt = get_datetime(fp)
        if dt:
            dates.append(dt)

    if dates:
        start = min(dates).strftime("%m-%d")
        end   = max(dates).strftime("%m-%d")
        if start == end:
            return start
        return f"{start}_to_{end}"

    return "unsorted"

def move_file(src, dest_dir):
    """Move a file to dest_dir, skipping if destination already exists."""
    os.makedirs(dest_dir, exist_ok=True)
    dst = os.path.join(dest_dir, os.path.basename(src))
    if os.path.exists(dst):
        log.warning(f"SKIP (exists): {dst}")
        return False
    shutil.move(src, dst)
    return True

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info(f"Organized dir:    {ORGANIZED_DIR}")
    log.info(f"Cluster gap:      {CLUSTER_GAP_MINUTES} minutes")
    log.info(f"Coord precision:  {COORD_PRECISION} decimal places")

    total_moved = 0
    total_clusters = 0

    for year in sorted(os.listdir(ORGANIZED_DIR)):
        year_path = os.path.join(ORGANIZED_DIR, year)
        if not os.path.isdir(year_path) or not year.isdigit():
            continue

        for month in sorted(os.listdir(year_path)):
            month_path = os.path.join(year_path, month)
            if not os.path.isdir(month_path):
                continue

            # Only process files directly in the month folder
            # (skip files already in subfolders -- allows safe reruns)
            files = [
                os.path.join(month_path, f)
                for f in os.listdir(month_path)
                if os.path.isfile(os.path.join(month_path, f))
                and not f.startswith('.')
            ]

            if not files:
                continue

            log.info(f"\nProcessing {year}/{month} ({len(files)} files)...")

            # Get timestamps for all files
            file_times = []
            no_date = []
            for fp in files:
                dt = get_datetime(fp)
                if dt:
                    file_times.append((fp, dt))
                else:
                    no_date.append(fp)

            # Sort by timestamp
            file_times.sort(key=lambda x: x[1])

            # Cluster by time gap
            clusters = cluster_by_time(file_times, CLUSTER_GAP_MINUTES)

            # Files with no date go into their own cluster
            if no_date:
                clusters.append(no_date)
                log.warning(f"  {len(no_date)} files had no date, grouped as separate cluster")

            total_clusters += len(clusters)
            log.info(f"  {len(clusters)} clusters found")

            # Name and move each cluster
            for cluster in clusters:
                folder_name = name_for_cluster(cluster, month_path)
                dest_dir = os.path.join(month_path, folder_name)
                log.info(f"  Cluster of {len(cluster)} -> {folder_name}/")

                for fp in cluster:
                    if move_file(fp, dest_dir):
                        total_moved += 1

    log.info(f"\nDone. {total_moved} files moved into {total_clusters} clusters.")

if __name__ == "__main__":
    main()