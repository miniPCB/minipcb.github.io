import os
import json
from bs4 import BeautifulSoup

# Root folder for your miniPCB site
ROOT_DIR = "./"  
OUTPUT_FILE = "keywords.js"

# File extensions to process
HTML_EXTENSIONS = (".html", ".htm")

keywords_list = []

for root, _, files in os.walk(ROOT_DIR):
    for file in files:
        if file.endswith(HTML_EXTENSIONS):
            # Skip search.html explicitly
            if file.lower() == "search.html":
                continue

            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, ROOT_DIR).replace("\\", "/")

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    soup = BeautifulSoup(f, "html.parser")

                # Extract title
                title = soup.title.string.strip() if soup.title else ""

                # Extract meta keywords
                meta_tag = soup.find("meta", attrs={"name": "keywords"})
                meta_keywords = (
                    meta_tag["content"].strip() if meta_tag and "content" in meta_tag.attrs else ""
                )

                # Extract slogan
                slogan_tag = soup.find("p", class_="slogan")
                slogan = slogan_tag.get_text(strip=True) if slogan_tag else ""

                keywords_list.append({
                    "keyword": title,
                    "url": rel_path,
                    "meta": meta_keywords,
                    "slogan": slogan
                })

            except Exception as e:
                print(f"Error processing {file_path}: {e}")

# Write to keywords.js
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("const keywords = ")
    json.dump(keywords_list, f, indent=2)
    f.write(";")

print(f"✅ Keyword index built: {OUTPUT_FILE} with {len(keywords_list)} entries (excluding search.html)")
