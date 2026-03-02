#!/usr/bin/env python3
"""
Audit files in unknown/ folders to see if any have location data
that the geocoding script missed.

Usage: python3 audit_unknowns.py /path/to/organized

Outputs a summary of what tags were found, and lists files that
have GPS or location data that could potentially be geocoded.
"""

import os
import sys
import subprocess
import json
from collections import Counter

ORGANIZED_DIR = sys.argv[1] if len(sys.argv) > 1 else "./organized"

# Location-related tags to check beyond the ones we used
LOCATION_TAGS = [
    "GPSLatitude#",
    "GPSLongitude#", 
    "GPSLatitudeRef",
    "GPSLongitudeRef",
    "LocationName",
    "Location",
    "City",
    "State",
    "Country",
    "XMP:City",
    "XMP:Location",
    "IPTC:City",
    "IPTC:Country",
    "Keys:LocationName",  # Apple-specific
    "UserData:LocationName",  # Some video formats
]

has_gps = []
has_other_location = []
truly_unknown = []

unknown_files = []
for root, dirs, files in os.walk(ORGANIZED_DIR):
    if os.path.basename(root) == "unknown":
        for f in files:
            if not f.startswith('.'):
                unknown_files.append(os.path.join(root, f))

print(f"Found {len(unknown_files)} files in unknown folders\n")

for filepath in unknown_files:
    result = subprocess.run(
        ["exiftool", "-j"] + LOCATION_TAGS + [filepath],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)[0]
        data.pop("SourceFile", None)

        lat = data.get("GPSLatitude")
        lon = data.get("GPSLongitude")

        if lat is not None and lon is not None:
            has_gps.append((filepath, lat, lon))
        elif any(v for k, v in data.items() if k != "SourceFile"):
            has_other_location.append((filepath, data))
        else:
            truly_unknown.append(filepath)
    except (json.JSONDecodeError, IndexError):
        truly_unknown.append(filepath)

print(f"Has GPS (could be geocoded):     {len(has_gps)}")
print(f"Has other location tags:         {len(has_other_location)}")
print(f"Truly no location data:          {len(truly_unknown)}")

if has_gps:
    print(f"\nFirst 5 files with GPS that were missed:")
    for filepath, lat, lon in has_gps[:5]:
        print(f"  {os.path.basename(filepath)}: {lat}, {lon}")

if has_other_location:
    print(f"\nFirst 5 files with other location tags:")
    for filepath, tags in has_other_location[:5]:
        print(f"  {os.path.basename(filepath)}: {tags}")