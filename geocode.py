#!/usr/bin/env python3
"""
Sort photos into location subfolders within each month directory.
Transforms: organized/YYYY/MM/photo.jpg
       into: organized/YYYY/MM/City-CC/photo.jpg

Photos without GPS data are moved to organized/YYYY/MM/unknown/

Usage: python3 geoname.py /path/to/organized
Requirements: pip3 install geopy --break-system-packages
              exiftool must be installed (brew install exiftool)
"""

import os
import sys
import time
import subprocess
import json
import shutil
from geopy.geocoders import Nominatim

ORGANIZED_DIR = sys.argv[1] if len(sys.argv) > 1 else "./organized"

# Nominatim (OpenStreetMap) requires at least 1 second between requests
# to avoid being banned. Do not reduce this value.
DELAY = 1.1

# Cache geocoding results to avoid redundant API calls for photos
# taken in the same area (e.g. many photos from same hotel/location)
geo_cache = {}

def get_gps(filepath):
    """Extract GPS coordinates from a file using exiftool.
    Returns (latitude, longitude) tuple or None if no GPS data.
    Uses GPSLatitude/Longitude in decimal degrees with ref direction."""
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
    """Round coordinates to reduce redundant API calls.
    Precision 2 groups photos within roughly 1km of each other."""
    return (round(coords[0], precision), round(coords[1], precision))

def get_location_name(coords):
    """Reverse geocode coordinates to a City-CC string.
    Results are cached to minimize API calls.
    Returns a string like 'Bangkok-TH' or 'Unknown' if lookup fails."""
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

    geo_cache[rounded] = "Unknown"
    return "Unknown"

def move_file(filepath, dest_dir):
    """Move a file to dest_dir, creating the directory if needed.
    If a file with the same name exists in dest_dir, skip and warn."""
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, os.path.basename(filepath))
    if os.path.exists(dest_path):
        print(f"  WARNING: {os.path.basename(filepath)} already exists in {dest_dir}, skipping")
        return
    shutil.move(filepath, dest_path)

# Walk through each year/month directory
for year in sorted(os.listdir(ORGANIZED_DIR)):
    year_path = os.path.join(ORGANIZED_DIR, year)
    if not os.path.isdir(year_path) or not year.isdigit():
        continue

    for month in sorted(os.listdir(year_path)):
        month_path = os.path.join(year_path, month)
        if not os.path.isdir(month_path):
            continue

        print(f"\nProcessing {year}/{month}...")

        # Get all files directly in this month folder (not in subfolders)
        files = [f for f in os.listdir(month_path)
                 if os.path.isfile(os.path.join(month_path, f))
                 and not f.startswith('.')]

        for filename in files:
            filepath = os.path.join(month_path, filename)
            coords = get_gps(filepath)

            if coords:
                location = get_location_name(coords)
            else:
                # No GPS data -- received via text, downloaded, or location services was off
                location = "unknown"

            dest_dir = os.path.join(month_path, location)
            print(f"  {filename} -> {location}/")
            move_file(filepath, dest_dir)
