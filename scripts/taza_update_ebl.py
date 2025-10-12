#!/usr/bin/env python3
# mi_taza_update_ebl.py
# Builds/updates EBL.json (Engineering Build Log) and ALWAYS preserves:
# - existing status
# - existing build_date
# - existing rev  (← NEW: keep the previously recorded rev if present)

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PN_HTML_RE = re.compile(r'^([0-9]{2}[A-Z]-\d{1,3})\.html$', re.IGNORECASE)
TITLE_RE = re.compile(r'<title>(.*?)</title>', re.IGNORECASE | re.DOTALL)
REV_RE = re.compile(r'^(?P<letter>[A-Z]+)(?P<maj>\d+)-(?P<min>\d+)$', re.IGNORECASE)
SCH_MD_RE = re.compile(r'^(?P<pn>[^_/\\]+)_(?P<rev>[^_/\\]+)_(?:sch|shc)\.md$', re.IGNORECASE)

STATUSES = ("not planned", "planned", "in-progress", "complete")

def _default_root() -> Path:
    here = Path(__file__).resolve()
    return here.parent.parent if here.parent.name.lower() == "scripts" else Path.cwd()

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build EBL.json (Engineering Build Log) from site files.")
    p.add_argument("input", nargs="?", help="Optional path to a PN_REV_sch.md or PN.html to restrict to that board.")
    p.add_argument("--root", type=Path, default=None, help="Project root (default: inferred from script location).")
    p.add_argument("-o", "--out", type=Path, default=None, help="Output path for EBL.json (default: <root>/EBL.json).")
    return p.parse_args()

def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def clean_title(raw_title: str, pn: str) -> str:
    t = (raw_title or "").strip()
    if "|" in t:
        right = t.split("|", 1)[1].strip()
        if right:
            return right
    if t.upper().startswith(pn.upper()):
        t2 = t[len(pn):].lstrip(" -–|:").strip()
        if t2:
            return t2
    return t

def find_board_pages(root: Path) -> Dict[str, Tuple[Path, str]]:
    """Return { pn: (path, title) } for files like 04B-005.html, 20A-30.html."""
    result: Dict[str, Tuple[Path, str]] = {}
    for dirpath, _, files in os.walk(root):
        for fname in files:
            if not fname.lower().endswith(".html"):
                continue
            m = PN_HTML_RE.match(fname)
            if not m:
                continue
            pn = m.group(1).upper()
            fp = Path(dirpath) / fname
            html = read_text(fp)
            mt = TITLE_RE.search(html)
            title = clean_title(mt.group(1).strip() if mt else "", pn)
            # prefer shortest relative path if duplicates
            rel = fp.relative_to(root)
            if pn in result:
                prev_path, _ = result[pn]
                if len(str(rel)) >= len(str(prev_path.relative_to(root))):
                    continue
            result[pn] = (fp, title)
    return result

def rev_key(rev: str) -> Tuple[int, int, int]:
    """Sort key for 'A1-01', 'B2-3'. Invalids sort last."""
    m = REV_RE.match((rev or "").strip())
    if not m:
        return (999, 999999, 999999)
    letters = m.group("letter").upper()
    base = 0
    for ch in letters:
        base = base * 26 + (ord(ch) - ord("A") + 1)
    return (base, int(m.group("maj")), int(m.group("min")))

def discover_latest_revs(root: Path) -> Dict[str, str]:
    """Return { pn: latest_rev } by scanning *_sch.md."""
    latest: Dict[str, str] = {}
    for dirpath, _, files in os.walk(root):
        for fname in files:
            if not fname.lower().endswith(("_sch.md", "_shc.md")):
                continue
            m = SCH_MD_RE.match(fname)
            if not m:
                continue
            pn = m.group("pn").upper()
            rev = m.group("rev")
            cur = latest.get(pn)
            if not cur or rev_key(rev) > rev_key(cur):
                latest[pn] = rev
    return latest

def load_existing_ebl(path: Path) -> Tuple[Dict[Tuple[str, str], Dict], Dict[str, Dict]]:
    """
    Load existing EBL.json and index two ways:
      by_pair:  {(board, rev): row}
      by_board: {board: row}  (first occurrence wins)
    """
    by_pair: Dict[Tuple[str, str], Dict] = {}
    by_board: Dict[str, Dict] = {}
    if not path.exists():
        return by_pair, by_board
    try:
        data = json.loads(read_text(path)) or []
        if isinstance(data, list):
            for row in data:
                board = str(row.get("board", "")).upper()
                rev = str(row.get("rev", "")).strip()
                by_pair[(board, rev)] = row
                if board and board not in by_board:
                    by_board[board] = row
    except Exception:
        pass
    return by_pair, by_board

def build_ebl_entries(
    root: Path,
    restrict_pn: Optional[str],
    existing_by_pair: Dict[Tuple[str, str], Dict],
    existing_by_board: Dict[str, Dict],
) -> List[Dict]:
    pages = find_board_pages(root)
    revs = discover_latest_revs(root)

    entries: List[Dict] = []
    for pn, (fp, title) in pages.items():
        if restrict_pn and pn.upper() != restrict_pn.upper():
            continue
        rel_link = "./" + str(fp.relative_to(root)).replace("\\", "/")

        # --- Preserve REV if we already have an entry for this board ---
        preserved_entry = existing_by_board.get(pn, {})
        preserved_rev = (preserved_entry.get("rev") or "").strip()
        discovered_latest_rev = revs.get(pn, "")

        rev_to_use = preserved_rev if preserved_rev else discovered_latest_rev

        # Preserve status/build_date attached to that (board, rev)
        prev = existing_by_pair.get((pn, rev_to_use), {})
        status = prev.get("status", "not planned")
        build_date = prev.get("build_date", "")

        if status not in STATUSES:
            status = "not planned"

        entries.append({
            "build_date": build_date,
            "board": pn,
            "rev": rev_to_use,
            "title": title or "",
            "link": rel_link,
            "status": status
        })

    entries.sort(key=lambda d: (d["board"], rev_key(d["rev"])))
    return entries

def pn_from_input(path: str) -> Optional[str]:
    if not path:
        return None
    name = Path(path).name
    m = PN_HTML_RE.match(name)
    if m:
        return m.group(1).upper()
    m2 = SCH_MD_RE.match(name)
    if m2:
        return m2.group("pn").upper()
    return None

def main() -> int:
    args = parse_args()
    root = (args.root or _default_root()).resolve()
    out = (args.out or (root / "EBL.json")).resolve()

    restrict_pn = pn_from_input(args.input) if args.input else None
    existing_by_pair, existing_by_board = load_existing_ebl(out)  # ← preserves rev/status/build_date

    entries = build_ebl_entries(root, restrict_pn, existing_by_pair, existing_by_board)
    out.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"✅ Wrote {out} with {len(entries)} item(s).")
    if restrict_pn:
        print(f"(Restricted to PN: {restrict_pn})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
