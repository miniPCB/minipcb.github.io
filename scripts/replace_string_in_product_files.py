import os

folders = ["./00A", "./04A", "./04B", "./05", "./06", "./08H", "./09A", "./09H", "./10"]

def activate_schematic_tab(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    original = "<button class=\"tab\" onclick=\"showTab('schematic')\">Schematic</button>"
    replacement = "<button class=\"tab active\" onclick=\"showTab('schematic')\">Schematic</button>"

    if original in html:
        html = html.replace(original, replacement)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[UPDATED] {filepath}")

def run():
    for folder in folders:
        for file in os.listdir(folder):
            if file.endswith(".html"):
                activate_schematic_tab(os.path.join(folder, file))

if __name__ == "__main__":
    run()
