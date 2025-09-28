#!/usr/bin/env python3
"""
taza_export_title_list.py
Export a text file containing the HTML <title> values across your website.

Default root:  C:\\Repos\\minipcb.github.io\\
Default output: <root>\\titles.txt

Examples:
  # simplest (uses defaults)
  python scripts/taza_export_title_list.py

  # write titles + relative paths, sorted by title, unique
  python scripts/taza_export_title_list.py --with-paths --sort title --unique

  # custom root and output
  python scripts/taza_export_title_list.py --root "C:\\Repos\\minipcb.github.io" --out "C:\\Repos\\minipcb.github.io\\_exports\\titles.txt"
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Optional, Tuple, List

DEFAULT_ROOT = r"C:\Repos\minipcb.github.io"
DEFAULT_OUT  = "titles.txt"

# Folders to skip while walking
DEFAULT_EXCLUDE_DIRS = {
    ".git", ".github", ".venv", "venv", "__pycache__", "node_modules",
    "scripts", "js", "assets", "images", "img", "dist", "build", "out"
}

HTML_EXTS = {".html", ".htm"}


def extract_title(text: str) -> Optional[str]:
    """
    Return the contents of the first <title>…</title> (without tags),
    or None if not found. Attempts BeautifulSoup if installed; falls back to regex.
    """
    # Try BeautifulSoup if present (best for robustness)
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(text, "html.parser")
        if soup.title and soup.title.string:
            return html.unescape(soup.title.string.strip())
    except Exception:
        pass

    # Fallback: regex (good enough for well-formed pages)
    m = re.search(r"<\s*title\s*>\s*(.*?)\s*<\s*/\s*title\s*>",
                  text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return html.unescape(m.group(1).strip())


def iter_html_files(root: Path, exclude_dirs: set[str]) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded directories in-place
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for fn in filenames:
            if Path(fn).suffix.lower() in HTML_EXTS:
                yield Path(dirpath) / fn


def stable_unique(items: Iterable[Tuple[str, Path]]) -> List[Tuple[str, Path]]:
    seen = set()
    out: List[Tuple[str, Path]] = []
    for title, p in items:
        if title not in seen:
            seen.add(title)
            out.append((title, p))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Export list of HTML <title> values.")
    ap.add_argument("--root", type=str, default=DEFAULT_ROOT,
                    help=f"Website root folder (default: {DEFAULT_ROOT})")
    ap.add_argument("--out", type=str, default=None,
                    help=f"Output file path (default: <root>\\{DEFAULT_OUT})")
    ap.add_argument("--with-paths", dest="with_paths", action="store_true",
                    help="Include relative page paths alongside titles.")
    ap.add_argument("--include-empty", dest="include_empty", action="store_true",
                    help="Include files that have no <title> (marked as '(no title)')).")
    ap.add_argument("--unique", action="store_true",
                    help="De-duplicate by title (first occurrence kept).")
    ap.add_argument("--sort", choices=["none", "title", "path"], default="none",
                    help="Sort output (default: none).")
    ap.add_argument("--exclude-dirs", type=str, nargs="*", default=sorted(DEFAULT_EXCLUDE_DIRS),
                    help="Additional directory names to exclude while walking.")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[ERROR] Root does not exist: {root}", file=sys.stderr)
        return 2

    out_path = Path(args.out) if args.out else (root / DEFAULT_OUT)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    records: List[Tuple[str, Path]] = []
    total_files = 0
    for html_path in iter_html_files(root, set(args.exclude_dirs)):
        total_files += 1
        try:
            text = html_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"[WARN] Could not read {html_path}: {e}", file=sys.stderr)
            continue

        title = extract_title(text)
        if not title:
            if args.include_empty:
                title = "(no title)"
            else:
                continue

        rel = html_path.relative_to(root)
        records.append((title, rel))

    if args.unique:
        records = stable_unique(records)

    if args.sort == "title":
        records.sort(key=lambda t: t[0].lower())
    elif args.sort == "path":
        records.sort(key=lambda t: str(t[1]).lower())

    # Write
    try:
        with out_path.open("w", encoding="utf-8", newline="\n") as f:
            if args.with_paths:
                for title, rel in records:
                    f.write(f"{rel} | {title}\n")
            else:
                for title, _ in records:
                    f.write(f"{title}\n")
    except Exception as e:
        print(f"[ERROR] Failed to write output: {e}", file=sys.stderr)
        return 3

    kept = len(records)
    print(f"[OK] Scanned {total_files} HTML file(s). Wrote {kept} line(s) -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
