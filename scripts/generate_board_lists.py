import os
import re
import json

# List of folders to scan
catalog = ["00A", "04A", "04B", "05", "06", "09A", "09D", "09H", "08D", "08G", "08H", "10", "11"]

# Match filenames like '123-45.html', '12A-345.html' (3 alphanumeric + dash + 2–3 digits)
pattern = re.compile(r"^[A-Z0-9]{3}-\d{2,3}\.html$", re.IGNORECASE)

# Base directory is one level above this script
script_dir = os.path.abspath(os.path.dirname(__file__))

manifest = {}

# Scan each folder
for folder in catalog:
    folder_path = os.path.join(script_dir, "..", folder)
    print(f"\nScanning folder: {os.path.abspath(folder_path)}")

    try:
        files = os.listdir(folder_path)
        matching_files = []

        for f in sorted(files):
            if pattern.match(f):
                print(f"  ✔ Match: {f}")
                matching_files.append(f)
            else:
                print(f"  ✖ Skip : {f}")

        manifest[folder] = len(matching_files)
        print(f"  → {manifest[folder]} file(s) matched.")

    except FileNotFoundError:
        print(f"  ⚠ Folder not found: {folder}")
        manifest[folder] = 0

# Add total count
total = sum(manifest.values())
manifest["TOTAL"] = total

# Write JSON to project root or same folder (your choice)
output_path = os.path.join(script_dir, "..", "file_manifest.json")
with open(output_path, "w") as f:
    json.dump(manifest, f, indent=2, sort_keys=True)

# Print final summary
print("\nSummary:")
for folder in catalog:
    print(f"{folder}: {manifest[folder]} file(s)")
print(f"TOTAL: {manifest['TOTAL']} file(s)")
