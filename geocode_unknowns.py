#!/usr/bin/env python3
"""
Retry geocoding for files in unknown/ subfolders.
Uses fixed GPS extraction that returns numeric values.
Files with GPS get moved to a location subfolder (e.g. Bangkok-TH).
Files still without GPS stay in unknown/.

Usage: python3 retry_unknowns.py /path/to/organized
"""

import os
import sys
import time
import subprocess
import json
import shutil
from geopy.geocoders import Nominatim

ORGANIZED_DIR = sys.argv[1] if len(sys.argv) > 1 else "./organized"
DELAY = 1.1
geo_cache = {}

def get_gps(filepath):
    """Extract GPS as numeric values using # suffix to avoid string format."""
    result = subprocess.run(
        ["exiftool", "-j", "-GPSLatitude#", "-GPSLongitude#", filepath],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)
        lat = data[0].get("GPSLatitude")
        lon = data[0].get("GPSLongitude")
        if lat is not None and lon is not None:
            return (float(lat), float(lon))
    except (json.JSONDecodeError, IndexError, KeyError, ValueError):
        pass
    return None

def round_coords(coords, precision=2):
    return (round(coords[0], precision), round(coords[1], precision))

def get_location_name(coords):
    rounded = round_coords(coords)
    if rounded in geo_cache:
        return geo_cache[rounded]
    geolocator = Nominatim(user_agent="photo_organizer")
    try:
        loc = geolocator.reverse(coords, language="en")
        time.sleep(DELAY)
        if loc:
            addr = loc.raw.get("address", {})
            city = (addr.get("city") or addr.get("town") or
                    addr.get("village") or addr.get("county") or "Unknown")
            country = addr.get("country_code", "").upper()
            name = f"{city}-{country}" if country else city
            geo_cache[rounded] = name
            return name
    except Exception as e:
        print(f"  Geocoding error: {e}")
        time.sleep(DELAY)
    geo_cache[rounded] = None
    return None

def move_file(filepath, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, os.path.basename(filepath))
    if os.path.exists(dest_path):
        print(f"  WARNING: {os.path.basename(filepath)} already exists, skipping")
        return
    shutil.move(filepath, dest_path)

moved = 0
stayed = 0

for root, dirs, files in os.walk(ORGANIZED_DIR):
    if os.path.basename(root) != "unknown":
        continue

    month_dir = os.path.dirname(root)
    print(f"\nProcessing {os.path.relpath(root, ORGANIZED_DIR)}...")

    for filename in files:
        if filename.startswith('.'):
            continue
        filepath = os.path.join(root, filename)
        coords = get_gps(filepath)
        if coords:
            location = get_location_name(coords)
            if location:
                dest_dir = os.path.join(month_dir, location)
                print(f"  {filename} -> {location}/")
                move_file(filepath, dest_dir)
                moved += 1
                continue
        stayed += 1

print(f"\nDone. Moved: {moved}, Still unknown: {stayed}")