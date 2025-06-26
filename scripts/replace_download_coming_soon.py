import os
import re

# Target folders (including top level)
folders = ["./00A", "./04A", "./04B", "./05", "./06", "./08H", "./09A", "./09H", "./10", "."]

# Pattern to match: <h2>Datasheet</h2> followed by a specific <a> link
pattern = re.compile(
    r'<h2>Datasheet</h2>\s*'
    r'<a href="\.\./datasheets/coming-soon\.html" target="_blank">Download Datasheet</a>',
    re.MULTILINE
)

# Replacement content
replacement = '''<h2>Comming Soon</h2>
<p>We are working on additional resources for this PCB. Please check back later!</p>'''

# Replace in all HTML files
for folder in folders:
    for root, _, files in os.walk(folder):
        for file in files:
            if file.endswith(".html"):
                path = os.path.join(root, file)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                new_content, count = pattern.subn(replacement, content)
                if count > 0:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    print(f"Updated: {path}")
