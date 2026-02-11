#!/usr/bin/env python3
"""
Global script (no file input): run when releasing a new board.

taza_board_release_procedure.py — One-click site housekeeping for a board release.

Runs, in order:
  1) generate_board_lists.py       (writes file_manifest.json in site root)
  2) generate_keywords_file.py     (writes keywords.js in site root)
  3) generate_scrollable_list.py   (writes schematics-data.js in site root)
  4) generate_site_index.py        (writes site_index.js in site root)

Notes:
- Steps (2-4) expect to run from the SITE ROOT (cwd="root"), so we set cwd=root for them.
- Step (1) writes output relative to the script folder's parent; cwd doesn't matter, but we set cwd=root anyway for consistency.
- Use --skip or --only to control which steps run.

Examples:
  python taza_board_release_procedure.py --root C:\Repos\minipcb.github.io
  python taza_board_release_procedure.py --root /path/to/minipcb --only keywords,siteindex
  python taza_board_release_procedure.py --root . --verbose
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# -------------------- CLI --------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run site-wide generators for a board release.")
    p.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],  # default: repo root (.. from /scripts)
        help="Site root directory (default: parent of this script folder).",
    )
    p.add_argument(
        "--scripts-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory containing generator scripts (default: this file's directory).",
    )
    p.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated subset of steps to run (aliases: lists,keywords,scrollable,siteindex).",
    )
    p.add_argument(
        "--skip",
        type=str,
        default="",
        help="Comma-separated steps to skip (aliases: lists,keywords,scrollable,siteindex).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print extra detail.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would run without executing.",
    )
    return p.parse_args()

# -------------------- Helpers --------------------

def banner(title: str, ch: str = "=", width: int = 80) -> str:
    line = ch * width
    return f"{line}\n{title}\n{line}"

def pretty_rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)

def ts() -> str:
    return time.strftime("%H:%M:%S")

def file_mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None

@dataclass
class Step:
    key: str
    title: str
    script_name: str
    cwd: str  # "root" or "scripts"
    expected_outputs: List[str]

# -------------------- Steps definition --------------------

STEPS: List[Step] = [
    Step(
        key="lists",
        title="Generate board lists",
        script_name="generate_board_lists.py",
        cwd="root",
        expected_outputs=["file_manifest.json"],
    ),
    Step(
        key="keywords",
        title="Generate keywords.js",
        script_name="generate_keywords_file.py",
        cwd="root",
        expected_outputs=["keywords.js"],
    ),
    Step(
        key="scrollable",
        title="Generate schematics-data.js",
        script_name="generate_scrollable_list.py",
        cwd="root",
        expected_outputs=["schematics-data.js"],
    ),
    Step(
        key="siteindex",
        title="Generate site_index.js",
        script_name="generate_site_index.py",
        cwd="root",
        expected_outputs=["site_index.js"],
    ),
]

ALIASES = {s.key: s.key for s in STEPS}

def parse_list(s: str) -> List[str]:
    return [x.strip().lower() for x in s.split(",") if x.strip()]

def filter_steps(only: List[str], skip: List[str]) -> List[Step]:
    if only:
        chosen_keys = set(only)
        return [s for s in STEPS if s.key in chosen_keys]
    if skip:
        skipped = set(skip)
        return [s for s in STEPS if s.key not in skipped]
    return list(STEPS)

# -------------------- Runner --------------------

def run_python_script(
    python_exe: str,
    script_path: Path,
    cwd: Path,
    verbose: bool = False,
    dry_run: bool = False,
) -> int:
    cmd = [python_exe, str(script_path)]
    if verbose or dry_run:
        print(f"[{ts()}] CMD: {' '.join(cmd)}")
        print(f"[{ts()}] CWD: {cwd}")
    if dry_run:
        return 0
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), check=False)
        return proc.returncode
    except FileNotFoundError:
        print(f"[ERR] Not found: {script_path}")
        return 127
    except Exception as e:
        print(f"[ERR] {e}")
        return 1

def resolve_outputs(outputs: List[str], root: Path, scripts_dir: Path, cwd_key: str) -> List[Path]:
    # All four scripts are intended to write into the site root.
    # (generate_board_lists.py uses parent of scripts dir, which *is* root.)
    # So we resolve into root for summary.
    return [root / name for name in outputs]

def step_cwd(root: Path, scripts_dir: Path, key: str) -> Path:
    if key in ("lists", "keywords", "scrollable", "siteindex"):
        return root
    return scripts_dir

def main() -> int:
    args = parse_args()
    python_exe = sys.executable
    root = args.root.resolve()
    scripts_dir = args.scripts_dir.resolve()

    print(banner("TAZA Board Release Procedure"))
    print(f"Site Root : {root}")
    print(f"Scripts   : {scripts_dir}")
    print(f"Python    : {python_exe}")
    if args.verbose:
        print(f"Only      : {args.only or '(none)'}")
        print(f"Skip      : {args.skip or '(none)'}")
    print()

    if not root.exists():
        print(f"[ERR] Site root not found: {root}")
        return 2
    if not scripts_dir.exists():
        print(f"[ERR] Scripts dir not found: {scripts_dir}")
        return 2

    only = parse_list(args.only)
    skip = parse_list(args.skip)
    steps = filter_steps(only, skip)
    if not steps:
        print("[ERR] No steps to run (check --only/--skip).")
        return 3

    # Preflight: ensure scripts exist
    missing: List[str] = []
    for s in steps:
        script_path = scripts_dir / s.script_name
        if not script_path.exists():
            missing.append(s.script_name)
    if missing:
        print("[ERR] Missing scripts:\n  - " + "\n  - ".join(missing))
        return 4

    # Track output mtimes before/after for a nice summary
    before_mtimes: Dict[str, Optional[float]] = {}
    after_mtimes: Dict[str, Optional[float]] = {}

    # Snapshot "before"
    for s in steps:
        for out in resolve_outputs(s.expected_outputs, root, scripts_dir, s.cwd):
            before_mtimes[out.name] = file_mtime(out)

    # Run
    for idx, s in enumerate(steps, start=1):
        script_path = scripts_dir / s.script_name
        cwd = step_cwd(root, scripts_dir, s.key)

        title = f"Step {idx}/{len(steps)} — {s.title} ({s.script_name})"
        print(banner(title))
        rc = run_python_script(python_exe, script_path, cwd, verbose=args.verbose, dry_run=args.dry_run)
        print(banner(f"Finished: {s.title} (exit {rc})"))
        print()
        if rc != 0:
            print(f"[WARN] Step '{s.key}' exited with code {rc}.")
            # Continue to next step; change to `return rc` if you prefer to stop on first error.

    # Snapshot "after"
    for s in steps:
        for out in resolve_outputs(s.expected_outputs, root, scripts_dir, s.cwd):
            after_mtimes[out.name] = file_mtime(out)

    # Summary
    print(banner("Summary"))
    for s in steps:
        outs = resolve_outputs(s.expected_outputs, root, scripts_dir, s.cwd)
        for out in outs:
            before = before_mtimes.get(out.name)
            after = after_mtimes.get(out.name)
            status: str
            if after is None:
                status = "NOT CREATED"
            elif before is None and after is not None:
                status = "CREATED"
            elif after and before and after > before:
                status = "UPDATED"
            else:
                status = "UNCHANGED"
            print(f"{out.name:<20} {status:>10}  ->  {pretty_rel(out, root)}")
    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
