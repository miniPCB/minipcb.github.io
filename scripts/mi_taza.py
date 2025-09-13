#!/usr/bin/env python3
"""
mi_taza.py — MiniPCB CLI with "depth" transitions + Select-All + Non-Interactive runs

New CLI:
- --all : select all *_sch.md files (no interactive 'A' needed)
- --script-index N : pick N-th script (1-based) and run immediately if selection present
- --script-name NAME : pick script by filename (exact → prefix → substring)
- --run-all-scripts : run every discovered script (table order) over the selection
- Non-interactive fast path: if you specify a script selector and a schematic selection
  (--all or --select), the tool runs immediately, with no prompts/menus.
- Use --no-clear to disable clears and pauses (good for CI/logs).

Existing features:
- Cross-platform screen clear
- Comma-separated script globs (e.g., "taza_*.py,tava_*.py")
- Verbose run banners
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Union

SCH_GLOB_DEFAULT = "*_sch.md"
SCRIPTS_GLOB_DEFAULT = "taza_*.py,tava_*.py"

def clear_screen(enabled: bool = True) -> None:
    if not enabled:
        return
    try:
        if sys.platform.startswith("win"):
            os.system("cls")
        else:
            os.system("clear")
        print("\033[2J\033[H", end="")
    except Exception:
        pass

# replace your pause() with this
def pause(enabled: bool = True, msg: str = "Press Enter to continue...") -> None:
    if not enabled or not sys.stdin.isatty():
        return
    try:
        input(msg)
    except EOFError:
        pass

def banner(title: str, ch: str = "=", width: int = 80) -> str:
    line = ch * width
    return f"{line}\n{title}\n{line}"

def first_line_doc(path: Path, max_chars: int = 120) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    for quote in ('"""', "'''"):
        if quote in text:
            start = text.find(quote)
            if start != -1:
                end = text.find(quote, start + 3)
                if end != -1:
                    doc = text[start + 3:end].strip().splitlines()
                    for line in doc:
                        s = line.strip()
                        if s:
                            return (s[:max_chars] + "…") if len(s) > max_chars else s
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            s = s.lstrip("#").strip()
            if s:
                return (s[:max_chars] + "…") if len(s) > max_chars else s
    return ""

def split_pn_rev_from_filename(p: Path) -> Tuple[str, str]:
    stem = p.stem
    parts = stem.split("_")
    pn, rev = "?", "?"
    if len(parts) >= 3 and parts[-1].lower() == "sch":
        pn = parts[0]; rev = parts[1]
    elif len(parts) >= 2:
        pn = parts[0]; rev = parts[1]
    return pn, rev

def _expand_globs(globs_str: str):
    return [g.strip() for g in globs_str.split(",") if g.strip()]

def find_sch_files(root: Path, sch_glob: str, limit: int) -> List[Path]:
    files = sorted(root.rglob(sch_glob))
    if limit and limit > 0:
        files = files[:limit]
    return files

def list_scripts(scripts_dir: Path, scripts_glob: str):
    if not scripts_dir.exists():
        return []
    results = []
    seen = set()
    for pat in _expand_globs(scripts_glob):
        for p in sorted(scripts_dir.glob(pat)):
            if p not in seen:
                seen.add(p)
                results.append((p, first_line_doc(p)))
    return results

def print_sch_table(files: List[Path]) -> None:
    if not files:
        print("No *_sch.md files found."); return
    print("\nDiscovered schematic markdown files:\n")
    print(f"{'#':>3}  {'PN':<12}  {'REV':<10}  PATH")
    print("-" * 70)
    for idx, f in enumerate(files, start=1):
        pn, rev = split_pn_rev_from_filename(f)
        print(f"{idx:>3}  {pn:<12}  {rev:<10}  {f}")

def print_scripts_table(items, scripts_dir: Path, pattern: str) -> None:
    print(f"\nScripts in {scripts_dir} matching {pattern}:\n")
    if not items:
        print("(none found)"); return
    print(f"{'#':>3}  {'SCRIPT':<32}  DESCRIPTION")
    print("-" * 90)
    for i, (p, desc) in enumerate(items, start=1):
        print(f"{i:>3}  {p.name:<32}  {desc}")

def print_menu(has_scripts: bool) -> None:
    if has_scripts:
        menu = """
Options:
  [#]  Run script
  [R]  Reselect schematic
  [C]  Change scripts dir
  [O]  Open scripts dir
  [Q]  Quit
"""
    else:
        menu = """
Options:
  [R]  Reselect schematic
  [C]  Change scripts dir
  [O]  Open scripts dir
  [Q]  Quit
"""
    print(menu.strip())

def open_folder(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as e:
        print(f"(Could not open folder: {e})")

def run_one(script_path: Path, sch: Path, clear_enabled: bool, pause_enabled: bool) -> int:
    clear_screen(clear_enabled)
    print(banner(f"RUNNING SCRIPT: {script_path.name}\nWITH SCHEMATIC: {sch}", "="))
    print()
    try:
        proc = subprocess.run(
            [sys.executable, str(script_path), str(sch)],
            cwd=str(script_path.parent),
            capture_output=False,
            text=False,
            check=False,
        )
        rc = proc.returncode
    except Exception as e:
        print(f"[ERR] Could not run {script_path.name}: {e}")
        pause(pause_enabled, "\nPress Enter to continue...")
        return 1
    print("\n" + banner(f"FINISHED: {script_path.name} (exit code {rc})\nOUTPUT TARGET: directory -> {script_path.parent}", "="))
    print()
    pause(pause_enabled, "Press Enter to continue...")
    return rc

def choose_script_by_name(scripts: List[Tuple[Path, str]], name: str) -> Optional[Path]:
    if not scripts or not name:
        return None
    # Exact
    for p, _ in scripts:
        if p.name == name:
            return p
    # Prefix
    for p, _ in scripts:
        if p.name.startswith(name):
            return p
    # Substring
    for p, _ in scripts:
        if name in p.name:
            return p
    return None

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="List *_sch.md then show & run scripts that process them.")
    p.add_argument("--root", type=Path, default=Path.cwd(), help="Project root for *_sch.md (default: CWD).")
    p.add_argument("--sch-glob", default=SCH_GLOB_DEFAULT, help=f"Glob for schematic MD (default: {SCH_GLOB_DEFAULT}).")
    p.add_argument("--scripts-dir", type=Path, default=None, help="Directory containing scripts (default: <root>/scripts).")
    p.add_argument("--scripts-glob", default=SCRIPTS_GLOB_DEFAULT, help=f"Script globs, comma-separated (default: {SCRIPTS_GLOB_DEFAULT}).")
    p.add_argument("--select", type=int, default=None, help="Non-interactive 1-based selection index for a single schematic.")
    p.add_argument("--all", action="store_true", help="Select all discovered schematics (non-interactive).")
    p.add_argument("--max", dest="max_items", type=int, default=9999, help="Limit how many schematics to display.")
    p.add_argument("--no-clear", action="store_true", help="Disable clears and pauses.")
    # Script selection for non-interactive runs:
    p.add_argument("--script-index", type=int, default=None, help="Pick N-th script (1-based) to run immediately.")
    p.add_argument("--script-name", type=str, default=None, help="Pick script by filename (exact→prefix→substring).")
    p.add_argument("--run-all-scripts", action="store_true", help="Run all discovered scripts over the selection.")
    p.add_argument("--batch", action="store_true", help="Shorthand for --all --run-all-scripts with no pauses/clears.")
    return p.parse_args()

def choose_index_or_all(n: int, prompt: str) -> Optional[Union[int, str]]:
    if n == 0:
        return None
    while True:
        choice = input(prompt).strip().lower()
        if choice == "":
            return None
        if choice == "a":
            return "all"
        if not choice.isdigit():
            print("Please enter a valid number or 'A' for all.")
            continue
        i = int(choice)
        if 1 <= i <= n:
            return i
        print(f"Enter a number between 1 and {n}, or 'A' for all.")

def run_batch(scripts_to_run: List[Path],
              selected_indices: List[int],
              sch_files: List[Path],
              no_clear: bool,
              step_mode: bool) -> int:
    if not scripts_to_run:
        print("[ERR] No scripts selected to run.")
        return 4
    total_jobs = len(scripts_to_run) * len(selected_indices)
    job = 0
    for script_path in scripts_to_run:
        for i, sel_idx in enumerate(selected_indices, start=1):
            job += 1
            sch = sch_files[sel_idx - 1]
            title = (
                f"RUN {job}/{total_jobs} — {script_path.name}"
                f"\nWITH SCHEMATIC: {sch}"
            )
            clear_screen(not no_clear)
            print(banner(title, "=")); print()
            try:
                subprocess.run(
                    [sys.executable, str(script_path), str(sch)],
                    cwd=str(script_path.parent),
                    capture_output=False,
                    text=False,
                    check=False,
                )
                rc = 0
            except Exception as e:
                print(f"[ERR] Could not run {script_path.name}: {e}")
                rc = 1
            print("\n" + banner(f"FINISHED ({job}/{total_jobs}): exit {rc}", "=")); print()
            # Pause between schematics only in step-through mode
            if step_mode and i != len(selected_indices):
                pause(not no_clear, "Press Enter for next schematic...")
    # Final pause only in step-through mode
    if step_mode:
        pause(not no_clear, "All runs finished. Press Enter to return...")
    return 0

def main() -> int:
    args = parse_args()

    # Derive step/consecutive from flags (step wins if both given)
    step_mode = bool(getattr(args, "step", False) and not getattr(args, "consecutive", False))

    # Optional one-switch batch: expand to flags
    if getattr(args, "batch", False):
        args.all = True
        args.run_all_scripts = True
        # Only force no_clear if not stepping; in step-through we allow pauses
        if not step_mode:
            args.no_clear = True

    root: Path = args.root.resolve()
    scripts_dir: Path = (args.scripts_dir or (root / "scripts")).resolve()

    if not root.exists():
        print(f"Root directory not found: {root}", file=sys.stderr)
        return 2

    clear_screen(not args.no_clear)
    sch_files = find_sch_files(root, args.sch_glob, args.max_items)
    print_sch_table(sch_files)
    if not sch_files:
        return 0

    # Build selection (may be interactive)
    selected_indices: List[int]
    if args.all:
        selected_indices = list(range(1, len(sch_files) + 1))
    elif args.select is not None:
        if 1 <= args.select <= len(sch_files):
            selected_indices = [args.select]
        else:
            print(f"--select out of range (1..{len(sch_files)}).", file=sys.stderr)
            return 3
    else:
        sel = choose_index_or_all(len(sch_files), "\nSelect a file by number or 'A' for all (Enter to cancel): ")
        if sel is None:
            print("Cancelled."); return 0
        if sel == "all":
            selected_indices = list(range(1, len(sch_files) + 1))
        else:
            selected_indices = [int(sel)]

    # Discover scripts
    scripts = list_scripts(scripts_dir, args.scripts_glob)

    # ---------- Non-interactive fast path ----------
    scripts_to_run: List[Path] = []
    if getattr(args, "run_all_scripts", False):
        scripts_to_run = [p for (p, _) in scripts]
    elif args.script_index is not None:
        if 1 <= args.script_index <= len(scripts):
            scripts_to_run = [scripts[args.script_index - 1][0]]
        else:
            print(f"--script-index out of range (1..{len(scripts)}).", file=sys.stderr)
            return 5
    elif args.script_name:
        chosen = choose_script_by_name(scripts, args.script_name)
        if chosen:
            scripts_to_run = [chosen]
        else:
            print(f"--script-name '{args.script_name}' not found among discovered scripts.", file=sys.stderr)
            return 6

    if scripts_to_run:
        # In fast path, force fully non-interactive behavior unless user asked for step-through
        if not step_mode:
            args.no_clear = True
        return run_batch(scripts_to_run, selected_indices, sch_files, args.no_clear, step_mode)

    # ---------- Interactive path ----------
    while True:
        clear_screen(not args.no_clear)
        if len(selected_indices) == 1:
            chosen = sch_files[selected_indices[0] - 1]
            print(f"Selected: {chosen}\n")
        else:
            first = sch_files[selected_indices[0] - 1]
            print(f"Selected: {len(selected_indices)} schematics (first: {first})\n")

        print_scripts_table(scripts, scripts_dir, args.scripts_glob)

        mode_label = "Step-through" if step_mode else "Consecutive"
        if scripts:
            menu = f"""
Options:
  [#]  Run script on {len(selected_indices)} schematic(s)
  [T]  Toggle mode (currently: {mode_label})
  [R]  Reselect schematic(s)
  [C]  Change scripts dir
  [O]  Open scripts dir
  [Q]  Quit
""".strip()
        else:
            menu = f"""
Options:
  [T]  Toggle mode (currently: {mode_label})
  [R]  Reselect schematic(s)
  [C]  Change scripts dir
  [O]  Open scripts dir
  [Q]  Quit
""".strip()
        print(menu)

        choice = input("Enter choice (number/T/R/C/O/Q): ").strip().lower()

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(scripts):
                script_path = scripts[idx - 1][0]
                rc = run_batch([script_path], selected_indices, sch_files, args.no_clear, step_mode)
                if rc != 0:
                    return rc
                # rediscover scripts each loop in case folder changed externally
                scripts = list_scripts(scripts_dir, args.scripts_glob)
                continue
            else:
                print(f"Number out of range. Enter 1..{len(scripts)}."); pause(not args.no_clear); continue

        if choice in ("q", ""):
            return 0
        elif choice == "t":
            step_mode = not step_mode
        elif choice == "r":
            clear_screen(not args.no_clear)
            print_sch_table(sch_files)
            sel = choose_index_or_all(len(sch_files), "\nSelect a file by number or 'A' for all (Enter to cancel): ")
            if sel is None:
                continue
            if sel == "all":
                selected_indices = list(range(1, len(sch_files) + 1))
            else:
                selected_indices = [int(sel)]
        elif choice == "c":
            new_dir = input("Enter path to scripts directory (or press Enter to keep current): ").strip()
            if new_dir:
                scripts_dir = Path(new_dir).expanduser().resolve()
                print(f"Scripts directory set to: {scripts_dir}"); pause(not args.no_clear)
            scripts = list_scripts(scripts_dir, args.scripts_glob)
        elif choice == "o":
            print(f"Opening folder: {scripts_dir}"); open_folder(scripts_dir); pause(not args.no_clear)
        else:
            print("Unrecognized option. Choose a script number, T, R, C, O, or Q."); pause(not args.no_clear)

if __name__ == "__main__":
    sys.exit(main())
