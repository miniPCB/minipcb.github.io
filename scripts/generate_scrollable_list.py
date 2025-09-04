import os, re, html

out_path = "schematics-data.js"
title_re = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)

# Regex for part numbers like "04A-010", "09H-5", "00B-25"
partnum_re = re.compile(r"^[0-9]{2}[A-Z]-\d+")

items = []

# 🔎 Walk every subdirectory from current folder
for dirpath, _, files in os.walk("."):
    for f in files:
        if not f.lower().endswith(".html"):
            continue
        fp = os.path.join(dirpath, f)
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                html_txt = fh.read()
            m = title_re.search(html_txt)
            title = m.group(1).strip() if m else os.path.splitext(f)[0]
            rel = fp.replace("\\", "/").lstrip("./")

            # ✅ Only include if title starts with part number
            if not partnum_re.match(title):
                continue

            items.append((html.unescape(title), rel))
        except Exception:
            pass

items.sort(key=lambda x: x[0].lower())

with open(out_path, "w", encoding="utf-8") as out:
    out.write("window.SCHEMATICS = [\n")
    for t, p in items:
        out.write(f'  {{ title: {t!r}, href: {p!r} }},\n')
    out.write("];\n")

print(f"Wrote {out_path} with {len(items)} items.")
