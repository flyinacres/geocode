#!/usr/bin/env python3
"""
Retry geocoding for files in Unknown/ folders (capital U) -- these files
have GPS data but Nominatim returned no place name previously.

Improvements over original geocode script:
1. Finer coordinate rounding (3 decimal places, ~100m vs ~1km)
2. Progressive fallback: city -> town -> village -> suburb -> 
   county -> state -> country
3. If all else fails, uses "State-CC" or "CC" rather than Unknown

Usage: python3 retry_uppercase_unknown.py /path/to/organized
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

def round_coords(coords, precision=3):
    """Finer rounding than original script -- 3 decimal places is ~100m."""
    return (round(coords[0], precision), round(coords[1], precision))

def get_location_name(coords):
    """Progressive fallback through address fields to find any place name."""
    rounded = round_coords(coords)
    if rounded in geo_cache:
        return geo_cache[rounded]

    geolocator = Nominatim(user_agent="photo_organizer_retry")
    try:
        loc = geolocator.reverse(coords, language="en", zoom=14)
        time.sleep(DELAY)
        if loc:
            addr = loc.raw.get("address", {})
            country = addr.get("country_code", "").upper()

            # Try progressively broader place names
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
        return False
    shutil.move(filepath, dest_path)
    return True

moved = 0
stayed = 0

for root, dirs, files in os.walk(ORGANIZED_DIR):
    # Only process capital-U Unknown folders
    if os.path.basename(root) != "Unknown":
        continue

    month_dir = os.path.dirname(root)
    print(f"\nProcessing {os.path.relpath(root, ORGANIZED_DIR)}...")

    for filename in files:
        if filename.startswith('.'):
            continue
        filepath = os.path.join(root, filename)
        coords = get_gps(filepath)

        if not coords:
            print(f"  {filename} -> no GPS, leaving in Unknown/")
            stayed += 1
            continue

        location = get_location_name(coords)
        if location and location != "Unknown":
            dest_dir = os.path.join(month_dir, location)
            print(f"  {filename} -> {location}/")
            if move_file(filepath, dest_dir):
                moved += 1
        else:
            print(f"  {filename} -> no place name found, leaving in Unknown/")
            stayed += 1

print(f"\nDone. Moved: {moved}, Still Unknown: {stayed}")