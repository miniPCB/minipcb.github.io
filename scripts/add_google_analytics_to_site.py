import os
import re

folders = ["./00A", "./04A", "./04B", "./05", "./06", "./08H", "./09A", "./09H", "./10", "./collections"]

# Cleaned GA snippet
ga_snippet = """<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-9ZM2D6XGT2"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-9ZM2D6XGT2');
</script>
"""

# Regex to remove any existing Google Analytics gtag script block
ga_pattern = re.compile(
    r'<!-- Google tag \(gtag\.js\) -->.*?<script.*?</script>\s*<script>.*?gtag\(\'config\',\s*\'G-[A-Z0-9]+\'\);\s*</script>',
    re.DOTALL
)

def clean_and_insert_ga(html):
    # Remove existing GA snippet if found
    html = ga_pattern.sub('', html)

    # Insert after <head> (and only if it's not already there)
    if "googletagmanager.com/gtag/js" not in html:
        html = re.sub(r'(<head[^>]*>)', r'\1\n' + ga_snippet, html, count=1)

    return html

def process_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        original = f.read()

    updated = clean_and_insert_ga(original)

    if original != updated:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"[UPDATED] {filepath}")
    else:
        print(f"[SKIPPED] {filepath} already correct")

def run():
    # Top-level HTML files
    for file in os.listdir("."):
        if file.endswith(".html"):
            process_file(os.path.join(".", file))

    # Subfolder HTML files
    for folder in folders:
        if not os.path.isdir(folder):
            print(f"[SKIPPED] Folder not found: {folder}")
            continue
        for file in os.listdir(folder):
            if file.endswith(".html"):
                process_file(os.path.join(folder, file))

if __name__ == "__main__":
    run()
