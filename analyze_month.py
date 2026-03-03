#!/usr/bin/env python3
"""
Diagnostic script to analyze clustering results for a single month.
Shows timeline of files, their folder (named vs date-based), and
identifies gaps where date-named clusters are close to geocoded neighbors.

Usage: python3 analyze_month.py <month_path> [gap_minutes]
Example: python3 analyze_month.py "/Pictures/ii/org2/2026/02" 60
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timedelta

MONTH_PATH   = sys.argv[1]
GAP_MINUTES  = int(sys.argv[2]) if len(sys.argv) > 2 else 60

def get_datetime(filepath):
    result = subprocess.run(
        ["exiftool", "-j", "-DateTimeOriginal", "-CreationDate", "-CreateDate", "-FileModifyDate", filepath],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)[0]
        for field in ["DateTimeOriginal", "CreationDate", "CreateDate", "FileModifyDate"]:
            val = data.get(field)
            if val:
                clean = val.strip()[:19].replace(":", "-", 2)
                try:
                    return datetime.fromisoformat(clean)
                except ValueError:
                    continue
    except (json.JSONDecodeError, IndexError, KeyError):
        pass
    return None

def get_gps(filepath):
    result = subprocess.run(
        ["exiftool", "-j", "-GPSLatitude#", "-GPSLongitude#", filepath],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)[0]
        lat = data[0].get("GPSLatitude") if isinstance(data, list) else data.get("GPSLatitude")
        lon = data[0].get("GPSLongitude") if isinstance(data, list) else data.get("GPSLongitude")
        if lat is not None and lon is not None:
            return (float(lat), float(lon))
    except (json.JSONDecodeError, IndexError, KeyError, ValueError):
        pass
    return None

def is_date_folder(name):
    """Returns True if folder name looks like a date (MM-DD or MM-DD_to_MM-DD)."""
    parts = name.replace("_to_", "-").split("-")
    return all(p.isdigit() for p in parts)

# Collect all files with their folder, timestamp, and GPS
print(f"Scanning {MONTH_PATH}...\n")
records = []

for folder in sorted(os.listdir(MONTH_PATH)):
    folder_path = os.path.join(MONTH_PATH, folder)
    if not os.path.isdir(folder_path):
        continue
    folder_type = "DATE" if is_date_folder(folder) else "NAMED"
    for filename in sorted(os.listdir(folder_path)):
        if filename.startswith('.'):
            continue
        filepath = os.path.join(folder_path, filename)
        if not os.path.isfile(filepath):
            continue
        dt  = get_datetime(filepath)
        gps = get_gps(filepath)
        records.append({
            "file":    filename,
            "folder":  folder,
            "type":    folder_type,
            "dt":      dt,
            "has_gps": gps is not None,
        })

# Sort by timestamp
records.sort(key=lambda r: r["dt"] or datetime.min)

# Print timeline
print(f"{'Timestamp':<22} {'Folder':<30} {'Type':<6} {'GPS'}")
print("-" * 75)
prev_dt = None
for r in records:
    dt_str = r["dt"].strftime("%Y-%m-%d %H:%M:%S") if r["dt"] else "NO DATE"
    gps_str = "YES" if r["has_gps"] else "no"

    # Show gap from previous file
    if prev_dt and r["dt"]:
        gap = r["dt"] - prev_dt
        if gap > timedelta(minutes=GAP_MINUTES):
            print(f"  --- GAP: {int(gap.total_seconds()/60)} minutes ---")

    print(f"{dt_str:<22} {r['folder']:<30} {r['type']:<6} {gps_str}")
    prev_dt = r["dt"]

# Summary
print("\nSUMMARY")
print("-" * 40)
named  = [r for r in records if r["type"] == "NAMED"]
dated  = [r for r in records if r["type"] == "DATE"]
no_gps = [r for r in records if not r["has_gps"]]
print(f"Total files:          {len(records)}")
print(f"In named folders:     {len(named)}")
print(f"In date folders:      {len(dated)}")
print(f"Files without GPS:    {len(no_gps)}")

# Find date-named clusters adjacent to named clusters within gap window
print("\nDATE FOLDERS CLOSE TO NAMED NEIGHBORS (within gap window):")
print("-" * 40)
folders = {}
for r in records:
    if r["folder"] not in folders:
        folders[r["folder"]] = []
    folders[r["folder"]].append(r)

folder_names = list(dict.fromkeys(r["folder"] for r in records))  # ordered by first appearance

for i, fname in enumerate(folder_names):
    if not is_date_folder(fname):
        continue
    files = folders[fname]
    mid   = files[len(files)//2]["dt"]
    if not mid:
        continue

    # Check previous and next named folders
    prev_named = next((folder_names[j] for j in range(i-1, -1, -1)
                       if not is_date_folder(folder_names[j])), None)
    next_named = next((folder_names[j] for j in range(i+1, len(folder_names))
                       if not is_date_folder(folder_names[j])), None)

    def folder_midtime(fn):
        recs = folders.get(fn, [])
        times = [r["dt"] for r in recs if r["dt"]]
        if times:
            return times[len(times)//2]
        return None

    results = []
    if prev_named:
        pt = folder_midtime(prev_named)
        if pt and abs((mid - pt).total_seconds()) < GAP_MINUTES * 60:
            results.append(f"  prev: {prev_named} ({int(abs((mid-pt).total_seconds())/60)}min away)")
    if next_named:
        nt = folder_midtime(next_named)
        if nt and abs((mid - nt).total_seconds()) < GAP_MINUTES * 60:
            results.append(f"  next: {next_named} ({int(abs((mid-nt).total_seconds())/60)}min away)")

    if results:
        print(f"\n{fname} ({len(files)} files) could inherit:")
        for r in results:
            print(r)