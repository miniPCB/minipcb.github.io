#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
taza_generate_md_index.py

Scan <site_root>/md/ and generate <site_root>/index.json containing a list of
markdown files found there.

Usage:
  python taza_generate_md_index.py [site_root]

If site_root is omitted, tries to auto-detect a site root by looking for a folder
that contains "md/" and (styles.css or favicon.png).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


SKIP_DIRS = {
    ".git", ".github", ".vscode",
    "__pycache__", "node_modules",
    "venv", ".venv",
    "dist", "build",
}

MD_DIR_NAME = "md"


def should_skip_dir(p: Path) -> bool:
    parts = {x.lower() for x in p.parts}
    return any(d.lower() in parts for d in SKIP_DIRS)


def rel_posix(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def auto_detect_site_root(script_path: Path) -> Optional[Path]:
    """
    Heuristic:
      - has md/ directory
      - and either styles.css or favicon.png
    """
    candidates: List[Path] = []

    for base in [Path.cwd(), *Path.cwd().parents, script_path.parent, *script_path.parent.parents]:
        candidates.append(base)

    # Prefer a sibling "website" directory if it exists
    for base in list(dict.fromkeys(candidates)):
        w = base / "website"
        if w.exists() and w.is_dir():
            candidates.insert(0, w)

    def looks_like_site(root: Path) -> bool:
        if not root.exists() or not root.is_dir():
            return False
        if not (root / MD_DIR_NAME).exists():
            return False
        if not ((root / "styles.css").exists() or (root / "favicon.png").exists()):
            return False
        return True

    for root in list(dict.fromkeys(candidates)):
        try:
            if looks_like_site(root):
                return root.resolve()
        except Exception:
            continue

    return None


def parse_md_filename(stem: str) -> Dict[str, str]:
    """
    Optional convenience parsing (safe if your names don't match):
      - PN_REV_sch.md  -> pn=PN, rev=REV, kind=sch
      - PN_REV_man.md  -> kind=man
      - PN_REV_aut.md  -> kind=aut

    If it doesn't match, fields are blank.
    """
    parts = stem.split("_")
    out = {"pn": "", "rev": "", "kind": ""}
    if len(parts) >= 3:
        out["pn"] = parts[0].strip()
        out["rev"] = parts[1].strip()
        out["kind"] = parts[2].strip()
    return out


@dataclass
class MdEntry:
    path: str
    filename: str
    pn: str = ""
    rev: str = ""
    kind: str = ""
    mtime: str = ""


def build_md_index(site_root: Path) -> List[MdEntry]:
    md_root = site_root / MD_DIR_NAME
    entries: List[MdEntry] = []

    if not md_root.exists() or not md_root.is_dir():
        return entries

    for p in sorted(md_root.rglob("*.md")):
        if should_skip_dir(p.parent):
            continue

        meta = parse_md_filename(p.stem)
        try:
            mtime_iso = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        except Exception:
            mtime_iso = ""

        entries.append(
            MdEntry(
                path=rel_posix(site_root, p),
                filename=p.name,
                pn=meta["pn"],
                rev=meta["rev"],
                kind=meta["kind"],
                mtime=mtime_iso,
            )
        )

    return entries


def write_index_json(site_root: Path, entries: List[MdEntry], out_name: str = "index.json", pretty: bool = True) -> Path:
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "md_scan",
        "md_dir": MD_DIR_NAME,
        "count": len(entries),
        "entries": [asdict(e) for e in entries],
    }
    out_path = site_root / out_name
    out_path.write_text(json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Generate index.json by listing files in /md/")
    ap.add_argument("site_root", nargs="?", default=None, help="Path to site root (defaults to auto-detect).")
    ap.add_argument("-o", "--out", default="index.json", help="Output filename (default: index.json)")
    ap.add_argument("--min", action="store_true", help="Write minified JSON (no indentation).")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    script_path = Path(__file__).resolve()

    if args.site_root:
        site_root = Path(args.site_root).expanduser().resolve()
    else:
        detected = auto_detect_site_root(script_path)
        if not detected:
            print("ERROR: Could not auto-detect site root. Provide it explicitly:\n  python taza_generate_md_index.py <site_root>")
            return 2
        site_root = detected

    entries = build_md_index(site_root)
    out_path = write_index_json(site_root, entries, out_name=args.out, pretty=(not args.min))

    print(f"✅ Wrote: {out_path} ({len(entries)} entries)")
    md_root = site_root / MD_DIR_NAME
    if not md_root.exists():
        print(f"ℹ️  Note: {md_root} does not exist; wrote an empty index.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
