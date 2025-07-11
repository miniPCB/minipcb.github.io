import os
import re

# Directories to search (including top-level ".")
folders = ["./00A", "./04A", "./04B", "./05", "./06", "./08H", "./09A", "./09H", "./10", "."]

# --- Placeholder block to replace ---
placeholder_resources = re.compile(
    r'<div id="resources" class="tab-content">\s*'
    r'<h2>YouTube</h2>\s*<p>Coming soon\.\.\.</p>\s*'
    r'<h2>Wikipedia</h2>\s*<p>Coming soon\.\.\.</p>\s*'
    r'<h2>Instructables</h2>\s*<p>Coming soon\.\.\.</p>\s*'
    r'</div>',
    re.DOTALL | re.MULTILINE
)

# --- Final block to detect ---
final_block_generic = (
    r'<div id="{tab_id}" class="tab-content">\s*'
    r'<h2>Coming Soon</h2>\s*'
    r'<p>We are working on additional resources for this PCB\. Please check back later!</p>\s*'
    r'</div>'
)

# --- Tab button patterns ---
tab_button_pattern = lambda tab_id, label: re.compile(
    rf'\s*<button class="tab" onclick="showTab\(\'{tab_id}\'\)">{label}</button>\s*\n?',
    re.MULTILINE
)

# Replacement HTML for resources
replacement_resources = '''<div id="resources" class="tab-content">
<h2>Coming Soon</h2>
<p>We are working on additional resources for this PCB. Please check back later!</p>
</div>'''

# Process all HTML files
for folder in folders:
    for root, _, files in os.walk(folder):
        for file in files:
            if not file.endswith(".html"):
                continue

            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            updated = False
            changes = []

            # Replace placeholder "resources" block
            content, repl_count = placeholder_resources.subn(replacement_resources, content)
            if repl_count > 0:
                updated = True
                changes.append(f"replaced resources block")

            # Remove button if final block exists
            for tab_id, label in [("resources", "Additional Resources"), ("downloads", "Downloads")]:
                final_pattern = re.compile(final_block_generic.format(tab_id=tab_id), re.DOTALL | re.MULTILINE)
                button_pattern = tab_button_pattern(tab_id, label)

                if final_pattern.search(content):
                    content, btn_count = button_pattern.subn('', content)
                    if btn_count > 0:
                        updated = True
                        changes.append(f"removed {label.lower()} button")

            if updated:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"Updated {path}: {', '.join(changes)}")
