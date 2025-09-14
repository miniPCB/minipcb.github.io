#!/usr/bin/env python3
r"""
taza_update_copyright.py — Replace the year inside <footer>…© YYYY miniPCB. All rights reserved.…</footer>

Examples:
  # Scan whole site (HTML only), preview only
  python scripts/taza_update_copyright.py --root C:\Repos\minipcb.github.io --dry-run

  # Apply with backups
  python scripts/taza_update_copyright.py --root . --backup

  # Per-file (works when mi_taza passes a file path)
  python scripts/taza_update_copyright.py C:\Repos\minipcb.github.io\00A\00A-001.html
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# -------- Config --------
DEFAULT_EXTS = [".html", ".htm"]

# Match a <footer>…</footer> block (any attributes, any content)
FOOTER_RE = re.compile(
    r'(?P<open><footer\b[^>]*>)(?P<body>.*?)(?P<close></footer>)',
    re.IGNORECASE | re.DOTALL,
)

# Inside footer, find "© <year> miniPCB. All rights reserved."
# Preserve spaces around © and before "miniPCB" exactly as they appear.
COPY_LINE_RE = re.compile(
    r'(©\s*)(?:19|20)\d{2}(\s+miniPCB\. All rights reserved\.)',
    re.IGNORECASE,
)

@dataclass
class Change:
    path: Path
    lines_changed: int  # number of footer blocks updated in this file

# -------- Core logic --------
def update_footer_year(text: str, target_year: int) -> Tuple[str, int]:
    """Return (new_text, changes_count) updating only © YEAR miniPCB. All rights reserved. inside <footer> blocks."""

    changes = 0

    def _footer_repl(m: re.Match) -> str:
        nonlocal changes
        open_tag, body, close_tag = m.group('open'), m.group('body'), m.group('close')

        def _copy_repl(m2: re.Match) -> str:
            return f"{m2.group(1)}{target_year}{m2.group(2)}"

        new_body, n = COPY_LINE_RE.subn(_copy_repl, body, count=1)  # update first match in this footer
        if n:
            changes += 1
        return open_tag + new_body + close_tag

    new_text = FOOTER_RE.sub(_footer_repl, text)
    return new_text, changes

# -------- IO helpers --------
def _iter_html_files(root: Path, exts: List[str]) -> Iterable[Path]:
    exts_l = {e.lower() for e in exts}
    for dirpath, dirnames, filenames in os.walk(root):
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in exts_l:
                yield p

def _gather_from_paths(paths: List[Path], exts: List[str]) -> List[Path]:
    exts_l = {e.lower() for e in exts}
    out: List[Path] = []
    for raw in paths:
        p = raw.expanduser().resolve()
        if p.is_file():
            if p.suffix.lower() in exts_l:
                out.append(p)
        elif p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file() and sub.suffix.lower() in exts_l:
                    out.append(sub)
    return sorted(set(out))

def process_file(path: Path, target_year: int, encoding: str, dry_run: bool, backup: bool) -> Optional[Change]:
    try:
        text = path.read_text(encoding=encoding)
    except Exception:
        # best-effort fallback
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

    new_text, changed_blocks = update_footer_year(text, target_year)
    if changed_blocks == 0:
        return None

    if not dry_run:
        if backup:
            try:
                bak = path.with_suffix(path.suffix + ".bak")
                bak.write_text(text, encoding=encoding, errors="ignore")
            except Exception:
                pass
        try:
            path.write_text(new_text, encoding=encoding)
        except Exception:
            return None

    return Change(path=path, lines_changed=changed_blocks)

# -------- CLI --------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replace the year in © YYYY miniPCB. All rights reserved. inside <footer> blocks.")
    default_root = Path(__file__).resolve().parents[1]  # assume scripts/ under repo root
    p.add_argument("--root", type=Path, default=default_root, help=f"Site root (default: {default_root})")
    p.add_argument("--exts", type=str, default=",".join(DEFAULT_EXTS), help="Comma-separated extensions to scan (default: .html,.htm)")
    p.add_argument("--year", type=int, default=_dt.date.today().year, help="Target year (default: current year)")
    p.add_argument("--encoding", type=str, default="utf-8", help="Read/write encoding (default: utf-8)")
    p.add_argument("--dry-run", action="store_true", help="Scan and report, but do not write files")
    p.add_argument("--backup", action="store_true", help="Write .bak files before modifying")
    p.add_argument("paths", nargs="*", help="Optional file(s)/folder(s) to process (if omitted, scans --root)")
    return p.parse_args()

# -------- Main --------
def main() -> int:
    args = parse_args()
    exts = [e if e.startswith(".") else f".{e}" for e in (x.strip() for x in args.exts.split(",")) if e]
    targets: List[Path]

    if args.paths:
        targets = _gather_from_paths([Path(p) for p in args.paths], exts)
    else:
        root = args.root.resolve()
        if not root.exists():
            print(f"[err] root not found: {root}", file=sys.stderr)
            return 2
        targets = list(_iter_html_files(root, exts))

    scanned = len(targets)
    changes: List[Change] = []
    for path in targets:
        ch = process_file(path, args.year, args.encoding, args.dry_run, args.backup)
        if ch:
            changes.append(ch)

    print("=" * 72)
    print(f"Scanned HTML files : {scanned}")
    print(f"Files updated      : {len(changes)}")
    print(f"Footer blocks mod  : {sum(c.lines_changed for c in changes)}")
    if changes:
        print("\nUpdated:")
        for c in changes:
            print(f" - {c.path}  (+{c.lines_changed} footer)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
