import os

folders = ["./00A", "./04A", "./04B", "./05", "./06", "./08H", "./09A", "./09H", "./10"]

def fix_escaped_quotes(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    # Replace \'something\' → 'something'
    html_fixed = html.replace("\\'", "'")

    if html != html_fixed:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_fixed)
        print(f"[FIXED] {filepath}")

def run():
    for folder in folders:
        for file in os.listdir(folder):
            if file.endswith(".html"):
                fix_escaped_quotes(os.path.join(folder, file))

if __name__ == "__main__":
    run()
