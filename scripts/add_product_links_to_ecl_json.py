import json
import os

# Folders to search for product HTML files
folders = ["./04B", "./05", "./06", "./08H", "./09A", "./09H", "./10"]

# Load the ECL.json data
with open("ECL.json", "r", encoding="utf-8") as f:
    ecl_data = json.load(f)

# Build a map: board ID -> relative file path (like "04B/04B-005.html")
html_map = {}
for folder in folders:
    for file in os.listdir(folder):
        if file.endswith(".html"):
            board_id = os.path.splitext(file)[0]  # e.g., "04B-005"
            relative_path = os.path.join(folder, file).replace("\\", "/")
            html_map[board_id] = relative_path

# Update each ECL entry with the "link" field
for entry in ecl_data:
    board = entry["board"]
    entry["link"] = html_map.get(board, None)

# Save the modified JSON
with open("ECL.json", "w", encoding="utf-8") as f:
    json.dump(ecl_data, f, indent=2)
