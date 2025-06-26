import os

folders = ["./00A", "./04A", "./04B", "./05", "./06", "./08H", "./09A", "./09H", "./10"]

google_analytics_snippet = """<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-9ZM2D6XGT2"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-9ZM2D6XGT2');
</script>
"""

def add_google_analytics(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if "googletagmanager.com/gtag/js" in content:
        print(f"[SKIPPED] {filepath} already has Google Analytics.")
        return

    if "</head>" not in content:
        print(f"[SKIPPED] {filepath} has no </head> tag.")
        return

    updated_content = content.replace("</head>", f"{google_analytics_snippet}\n</head>")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print(f"[UPDATED] {filepath}")

def run():
    # Top-level .html files
    for filename in os.listdir("./"):
        if filename.endswith(".html"):
            add_google_analytics(os.path.join("./", filename))

    # Subfolder files
    for folder in folders:
        if not os.path.isdir(folder):
            print(f"[SKIPPED] Folder not found: {folder}")
            continue
        for filename in os.listdir(folder):
            if filename.endswith(".html"):
                add_google_analytics(os.path.join(folder, filename))

if __name__ == "__main__":
    run()
