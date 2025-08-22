import os, re, html

ROOTS = ["./00A","./02","./03","./04A","./04B","./04C","./05","./06","./08D","./08H","./09A","./09H","./09D","./10","./11","./collections"]
out_path = "schematics-data.js"
title_re = re.compile(r"<title>(.*?)</title>", re.IGNORECASE|re.DOTALL)

items = []
for root in ROOTS:
    if not os.path.isdir(root):
        continue
    for dirpath, _, files in os.walk(root):
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
