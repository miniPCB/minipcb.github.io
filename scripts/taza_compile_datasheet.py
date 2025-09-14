#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compile a datasheet-style Markdown from *_sch.md and *_man.md

taza_compile_datasheet.py

Pure compiler: merges content from a schematic export Markdown (*_sch.md or *_shc.md)
and a manual commentary Markdown (*_man.md) into a single datasheet-style Markdown.
No AI calls.

New:
- Built-in JSON preset for ordering/renaming/level shifts (no external JSON needed).
- Use --preset (default: "default") or --no-preset to disable.
- You can still add --order / --include / --exclude on top.

Examples
--------
# Use built-in preset (default) and write PN_REV.md
python taza_compile_datasheet.py path/to/04C-25_A1-01_sch.md

# Disable preset; just append SCH then MAN
python taza_compile_datasheet.py path/to/04C-25_A1-01_sch.md --no-preset

# Inspect headings
python taza_compile_datasheet.py path/to/04C-25_A1-01_sch.md --dump-headings

# Override ordering with DSL (still applies preset renames/level shifts unless --no-preset)
python taza_compile_datasheet.py path/to/04C-25_A1-01_sch.md \
  --order "man:Revision History, sch:Circuit Identification, man:Circuit Description, sch:Netlist (Schematic), sch:Partlist (Schematic), sch:Pinout Description Table, P1, *" \
  -o compiled.md --force

# Show the active preset JSON
python taza_compile_datasheet.py path/to/04C-25_A1-01_sch.md --show-preset

"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HEADING_RE = re.compile(r'^(?P<hash>#{1,6})\s+(?P<title>.+?)\s*$', re.UNICODE)
SCH_RE = re.compile(r'^(?P<pn>[^_/\\]+)_(?P<rev>[^_/\\]+)_(?:sch|shc)\.md$', re.IGNORECASE)
MAN_RE = re.compile(r'^(?P<pn>[^_/\\]+)_(?P<rev>[^_/\\]+)_man\.md$', re.IGNORECASE)

# ---------- Built-in presets ----------
PRESETS: Dict[str, Dict] = {
    "default": {
        "order": [
            {"src": "man", "match": "Revision History"},
            {"src": "sch", "match": "Circuit Identification"},
            {"src": "man", "match": "Circuit Description"},
            {"src": "sch", "match": "Netlist (Schematic)"},
            {"src": "sch", "match": "Partlist (Schematic)"},
            {"src": "sch", "match": "Pinout Description Table, P1"},
            {"src": "*"}
        ],
        "rename": {
            "sch:circuit identification": "Design Identification",
            "sch:pinout description table p1": "Connector Pinout — P1"
        },
        "level_shift": {
            "man:circuit description": -1
        },
        "exclude": [],
        "include": []
    }
}

def norm(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r'[^0-9a-z\s]+', ' ', s)
    s = re.sub(r'\s+', ' ', s)
    return s

@dataclass
class Section:
    src: str                   # 'sch' or 'man'
    level: int                 # 1..6
    title: str                 # raw title
    lines: List[str]           # including heading
    used: bool = False
    key: str = field(init=False)       # normalized title
    fqkey: str = field(init=False)     # normalized with src prefix e.g., "man:circuit description"

    def __post_init__(self):
        self.key = norm(self.title)
        self.fqkey = f"{self.src}:{self.key}"

def parse_markdown_sections(text: str, src: str) -> List[Section]:
    lines = text.splitlines()
    secs: List[Section] = []
    cur: Optional[Section] = None
    for line in lines:
        m = HEADING_RE.match(line)
        if m:
            if cur is not None:
                secs.append(cur)
            level = len(m.group('hash'))
            title = m.group('title').strip()
            cur = Section(src=src, level=level, title=title, lines=[line])
        else:
            if cur is None:
                # synthetic preamble
                cur = Section(src=src, level=1, title="_preamble", lines=["# _preamble"])
            cur.lines.append(line)
    if cur is not None:
        secs.append(cur)
    return secs

def derive_paths(input_path: Path) -> Tuple[Path, Path, str, str]:
    name = input_path.name
    m_sch = SCH_RE.match(name)
    m_man = MAN_RE.match(name)
    if m_sch:
        pn, rev = m_sch.group('pn'), m_sch.group('rev')
        sch = input_path
        man = input_path.parent / f"{pn}_{rev}_man.md"
    elif m_man:
        pn, rev = m_man.group('pn'), m_man.group('rev')
        man = input_path
        sch = input_path.parent / f"{pn}_{rev}_sch.md"
    else:
        raise ValueError(f"Filename must look like PN_REV_sch.md or PN_REV_man.md. Got: {name}")
    if not sch.exists():
        raise FileNotFoundError(f"Schematic file not found: {sch}")
    if not man.exists():
        raise FileNotFoundError(f"Manual file not found: {man}")
    return sch, man, pn, rev

def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except Exception as e:
        raise RuntimeError(f"Failed to read {path}: {e}")

def dump_headings(secs: List['Section']) -> List[str]:
    out = []
    for s in secs:
        out.append(f"{s.src}:{'#'*s.level} {s.title}")
    return out

def parse_list_arg(values: List[str]) -> List[str]:
    out: List[str] = []
    for v in values or []:
        parts = [p.strip() for p in v.split(',') if p.strip()]
        out.extend(parts)
    return out

def section_matches(sec: Section, token: str) -> bool:
    # token may be "src:title" or just "title"
    t = norm(token)
    if ':' in t:
        src, title = t.split(':', 1)
        return sec.src == src and sec.key == title
    return sec.key == t

def take_by_token(pool: List[Section], token: str) -> Optional[Section]:
    for s in pool:
        if not s.used and section_matches(s, token):
            s.used = True
            return s
    return None

def apply_order_dsl(order_str: str, sch_secs: List[Section], man_secs: List[Section]) -> List[Section]:
    out: List[Section] = []
    tokens = [t.strip() for t in order_str.split(',') if t.strip()]
    for tok in tokens:
        if tok == '*':
            for s in sch_secs:
                if not s.used:
                    s.used = True; out.append(s)
            for s in man_secs:
                if not s.used:
                    s.used = True; out.append(s)
            continue
        m = re.match(r'^(sch|man)\s*:\s*(.+)$', tok, re.IGNORECASE)
        if m:
            src = m.group(1).lower()
            name = m.group(2).strip()
            pool = sch_secs if src == 'sch' else man_secs
            s = take_by_token(pool, name)
            if s: out.append(s)
        else:
            # no src specified → match by title in both (sch first, then man)
            s = take_by_token(sch_secs, tok) or take_by_token(man_secs, tok)
            if s: out.append(s)
    return out

def apply_order_json(order_json: List[dict], sch_secs: List[Section], man_secs: List[Section]) -> List[Section]:
    out: List[Section] = []
    for item in order_json:
        src = (item.get('src') or '').lower()
        match = item.get('match', '')
        use_regex = bool(item.get('regex', False))
        if src == '*':
            for s in sch_secs:
                if not s.used:
                    s.used = True; out.append(s)
            for s in man_secs:
                if not s.used:
                    s.used = True; out.append(s)
            continue
        pool = sch_secs if src == 'sch' else man_secs if src == 'man' else (sch_secs + man_secs)
        if use_regex and match:
            rx = re.compile(match, re.IGNORECASE)
            for s in pool:
                if not s.used and rx.search(s.title):
                    s.used = True; out.append(s)
        else:
            token = f"{src}:{match}" if src in {'sch','man'} else match
            s = take_by_token(pool if src in {'sch','man'} else sch_secs, token) or (take_by_token(man_secs, token) if src not in {'sch','man'} else None)
            if s: out.append(s)
    return out

def filter_include_exclude(schs: List[Section], mans: List[Section], include: List[str], exclude: List[str]) -> Tuple[List[Section], List[Section]]:
    if include:
        include_norm = [norm(t) for t in include]
        def keep(sec: Section) -> bool:
            for t in include_norm:
                if section_matches(sec, t):
                    return True
            return False
        schs = [s for s in schs if keep(s)]
        mans = [s for s in mans if keep(s)]
    if exclude:
        exclude_norm = [norm(t) for t in exclude]
        def drop(sec: Section) -> bool:
            for t in exclude_norm:
                if section_matches(sec, t):
                    return True
            return False
        schs = [s for s in schs if not drop(s)]
        mans = [s for s in mans if not drop(s)]
    return schs, mans

def apply_renames_and_level_shifts(secs: List[Section], rename_map: Dict[str,str], level_shift: Dict[str,int]) -> None:
    for s in secs:
        key = s.fqkey  # e.g., "man:circuit description"
        # rename (src-qualified first, then generic)
        new_title = rename_map.get(key) or rename_map.get(s.key)
        if new_title:
            s.title = new_title
            s.key = norm(new_title)
            s.fqkey = f"{s.src}:{s.key}"
            m = HEADING_RE.match(s.lines[0])
            hashes = m.group('hash') if m else '#' * s.level
            s.lines[0] = f"{hashes} {new_title}"
        # level shift (src-qualified first, then generic)
        delta = level_shift.get(key) or level_shift.get(s.key) or 0
        if delta:
            new_level = min(6, max(1, s.level + int(delta)))
            if new_level != s.level:
                s.level = new_level
                s.lines[0] = f"{'#'*new_level} {s.title}"

def compile_sections(sch_secs: List[Section], man_secs: List[Section], order: str, order_json: Optional[List[dict]]) -> List[Section]:
    arranged: List[Section] = []
    if order_json is not None:
        arranged = apply_order_json(order_json, sch_secs, man_secs)
    elif order:
        arranged = apply_order_dsl(order, sch_secs, man_secs)
    # Append remaining (SCH then MAN)
    for s in sch_secs:
        if not s.used:
            s.used = True; arranged.append(s)
    for s in man_secs:
        if not s.used:
            s.used = True; arranged.append(s)
    return arranged

def main():
    ap = argparse.ArgumentParser(description="Compile a datasheet-style Markdown from *_sch.md and *_man.md with include/exclude/reorder/rename controls. No AI calls.")
    ap.add_argument("path", type=Path, help="Path to either *_sch.md or *_man.md")
    ap.add_argument("-o", "--out", type=Path, default=None, help="Output markdown path (default: PN_REV.md next to inputs)")
    ap.add_argument("--include", action="append", default=[], help="Sections to include (comma-separated or repeat). Tokens can be 'src:title' or 'title'")
    ap.add_argument("--exclude", action="append", default=[], help="Sections to exclude (comma-separated or repeat). Tokens can be 'src:title' or 'title'")
    ap.add_argument("--order", type=str, default="", help="Order DSL, e.g., 'man:Revision History, sch:Circuit Identification, *' (overrides preset order)")
    ap.add_argument("--preset", type=str, default="default", help=f"Built-in preset to apply first (available: {', '.join(PRESETS.keys())})")
    ap.add_argument("--no-preset", action="store_true", help="Disable presets entirely")
    ap.add_argument("--show-preset", action="store_true", help="Print the active preset JSON and exit")
    ap.add_argument("--dump-headings", action="store_true", help="Print detected headings (source:level title) and exit")
    ap.add_argument("--force", action="store_true", help="Overwrite output if it exists")
    args = ap.parse_args()

    sch_path, man_path, pn, rev = derive_paths(args.path)

    sch_text = load_text(sch_path)
    man_text = load_text(man_path)

    sch_secs = parse_markdown_sections(sch_text, 'sch')
    man_secs = parse_markdown_sections(man_text, 'man')

    if args.dump_headings:
        for line in dump_headings(sch_secs + man_secs):
            print(line)
        return

    # Active preset
    preset_cfg = {} if args.no_preset else PRESETS.get(args.preset or "", PRESETS["default"])

    if args.show_preset:
        print(json.dumps(preset_cfg, indent=2, ensure_ascii=False))
        return

    # Compose filters and transforms from preset + CLI
    order_json = preset_cfg.get("order") if preset_cfg else None
    rename_map: Dict[str,str] = {norm(k): v for k, v in (preset_cfg.get("rename", {}) if preset_cfg else {}).items()}
    level_shift: Dict[str,int] = {norm(k): int(v) for k, v in (preset_cfg.get("level_shift", {}) if preset_cfg else {}).items()}
    include = (preset_cfg.get("include", []) if preset_cfg else []) + parse_list_arg(args.include)
    exclude = (preset_cfg.get("exclude", []) if preset_cfg else []) + parse_list_arg(args.exclude)

    # Apply include/exclude filters
    sch_secs, man_secs = filter_include_exclude(sch_secs, man_secs, include, exclude)

    # Apply renames and level shifts from preset
    apply_renames_and_level_shifts(sch_secs + man_secs, rename_map, level_shift)

    # If user provided --order, it overrides preset order. Otherwise use preset order (if any).
    arranged = compile_sections(sch_secs, man_secs, args.order, order_json)

    # Build output
    header = f"# {pn} {rev} — Compiled Datasheet\n\n" \
             f"> Sources: `{sch_path.name}` (schematic export), `{man_path.name}` (manual commentary)\n\n"
    out_lines: List[str] = [header]
    for s in arranged:
        out_lines.append("\n".join(s.lines).rstrip())
        out_lines.append("")

    out_text = "\n".join(out_lines).rstrip() + "\n"
    out_path = args.out if args.out else sch_path.with_name(f"{pn}_{rev}.md")

    out_path = args.out if args.out else sch_path.with_name(f"{pn}_{rev}.md")
    # Always overwrite
    out_path.write_text(out_text, encoding='utf-8')
    print(f"✅ Wrote: {out_path}")

if __name__ == "__main__":
    main()
