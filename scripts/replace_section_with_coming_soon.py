import os
import re

# Directories to search
folders = ["./00A", "./04A", "./04B", "./05", "./06", "./08H", "./09A", "./09H", "./10", "."]  # includes top level

# What to find (note: whitespace and formatting ignored via regex)
pattern = re.compile(
    r'<div id="resources" class="tab-content">\s*'
    r'<h2>YouTube</h2><p>Coming soon\.\.\.</p>\s*'
    r'<h2>Wikipedia</h2><p>Coming soon\.\.\.</p>\s*'
    r'<h2>Instructables</h2><p>Coming soon\.\.\.</p>\s*'
    r'</div>', re.MULTILINE
)

# What to replace it with
replacement = '''<div id="resources" class="tab-content">
    <h2>Comming Soon</h2>
    <p>We are working on additional resources for this PCB. Please check back later!</p>
</div>'''

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
