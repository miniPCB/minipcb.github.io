import os
import re

folders = ["./00A", "./04A", "./04B", "./05", "./06", "./08H", "./09A", "./09H", "./10"]

def update_html_tab_default(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    # Step 1: Remove "active" from all tab buttons and tab-content divs
    html = re.sub(r'class="tab active"', 'class="tab"', html)
    html = re.sub(r'class="tab-content active"', 'class="tab-content"', html)

    # Step 2: Add "active" to the schematic tab button and content
    html = re.sub(
        r'(<button class="tab" onclick="showTab\(\'schematic\'\)">)',
        r'<button class="tab active" onclick="showTab(\'schematic\')">',
        html
    )
    html = re.sub(
        r'(<div id="schematic" class="tab-content")',
        r'<div id="schematic" class="tab-content active"',
        html
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[UPDATED] {filepath}")

def run():
    for folder in folders:
        for file in os.listdir(folder):
            if file.endswith(".html"):
                update_html_tab_default(os.path.join(folder, file))

if __name__ == "__main__":
    run()
