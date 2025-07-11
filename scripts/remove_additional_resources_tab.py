import os
import re

# Directories to search (including top-level ".")
folders = ["./00A", "./04A", "./04B", "./05", "./06", "./08H", "./09A", "./09H", "./10", "."]

# Regex pattern to match the placeholder resources block
placeholder_pattern = re.compile(
    r'<div id="resources" class="tab-content">\s*'
    r'<h2>YouTube</h2>\s*<p>Coming soon\.\.\.</p>\s*'
    r'<h2>Wikipedia</h2>\s*<p>Coming soon\.\.\.</p>\s*'
    r'<h2>Instructables</h2>\s*<p>Coming soon\.\.\.</p>\s*'
    r'</div>', 
    re.DOTALL | re.MULTILINE
)

# Final "Coming Soon" block to detect and insert
final_block = '''<div id="resources" class="tab-content">
    <h2>Coming Soon</h2>
    <p>We are working on additional resources for this PCB. Please check back later!</p>
</div>'''

# Regex to detect the final "Coming Soon" block
final_block_pattern = re.compile(
    r'<div id="resources" class="tab-content">\s*'
    r'<h2>Coming Soon</h2>\s*'
    r'<p>We are working on additional resources for this PCB\. Please check back later!</p>\s*'
    r'</div>',
    re.DOTALL | re.MULTILINE
)

# Regex to match the tab button
tab_button_pattern = re.compile(
    r'\s*<button class="tab" onclick="showTab\(\'resources\'\)">Additional Resources</button>\s*\n?',
    re.MULTILINE
)

# Process all HTML files in listed folders
for folder in folders:
    for root, _, files in os.walk(folder):
        for file in files:
            if file.endswith(".html"):
                path = os.path.join(root, file)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Replace placeholder block with final block
                content, replaced_count = placeholder_pattern.subn(final_block, content)

                # If final block is found, remove the tab button
                if final_block_pattern.search(content):
                    content, button_removed_count = tab_button_pattern.subn('', content)
                else:
                    button_removed_count = 0

                if replaced_count > 0 or button_removed_count > 0:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"Updated {path} ({replaced_count} replaced, {button_removed_count} button removed)")
