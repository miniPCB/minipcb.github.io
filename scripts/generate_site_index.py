import os
import json
from bs4 import BeautifulSoup

# Start from the current directory
root_folder = "."

site_index = []

def extract_metadata(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")
            title = soup.title.string.strip() if soup.title else os.path.basename(filepath)
            keywords_tag = soup.find("meta", attrs={"name": "keywords"})
            keywords = keywords_tag["content"] if keywords_tag else ""
            return title, keywords
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return os.path.basename(filepath), ""

# Walk through all subdirectories starting at root_folder
for root, _, files in os.walk(root_folder):
    for file in files:
        if file.endswith(".html"):
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, root_folder).replace("\\", "/")  # Ensure URL format
            title, keywords = extract_metadata(filepath)
            site_index.append({
                "title": title,
                "url": rel_path,
                "keywords": keywords
            })

# Output to JS file
output_file = "site_index.js"
with open(output_file, "w", encoding="utf-8") as f:
    f.write("const siteIndex = ")
    json.dump(site_index, f, indent=2)
    f.write(";")

print(f"✅ siteIndex generated with {len(site_index)} entries → {output_file}")
