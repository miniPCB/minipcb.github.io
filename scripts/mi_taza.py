#!/usr/bin/env python3
"""
mi_taza.py — MiniPCB CLI with Welcome screen + robust discovery + per-file, bulk & standalone script runs.

Features:
- Welcome screen: Scan Markdown (schematic/compiled), Scan HTML (part pages/all), or go straight to scripts.
- Repo-wide HTML discovery (no PART_DIR_PREFIXES).
- Part-page finder:
    * Matches 1-2 digit families with optional letters (02, 02A, 09H, etc.).
    * Accepts .htm/.html (any case).
    * Ancestor folder match allows numeric-root families and decorated folder names.
    * Works for files like 02A-00.html under 02/.
- Scripts list excludes generate_*.py by default (use --scripts-glob to include).
- --max defaults to 99999 so you don't get stuck at 64.
- NEW: --bulk to run the chosen script ONCE, passing ALL selected files as positional args.
       (If the command line would be too long on Windows, Mi Taza passes a temporary manifest via --paths-file.)

Behavior:
- Standalone and Bulk: one run, optional single pause/clear at the end (unless --no-clear).
- Per-file (consecutive): no pauses/clears between files; a single pause/clear at the very end only.
- Per-file (step-through): prompts between files as before.

Debug:
- --debug-discovery shows why HTML files were skipped (regex/ancestor).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple, Union

# ---------------- Config ----------------
SCH_GLOB_DEFAULT = "*_sch.md"
SCRIPTS_GLOB_DEFAULT = "taza_*.py,tava_*.py"  # no generate_*.py by default

# Compiled datasheet pattern: PN_REV.md (exclude typical *_X.md aux files)
DS_RE = re.compile(r"^(?P<pn>[^_/\\]+)_(?P<rev>[^_/\\]+)\.md$", re.IGNORECASE)

# Part-number in HTML filenames:
# - prefix: 1-2 digits + optional letters (e.g., 02, 2, 04A, 09H)
# - dash, then digits (part number), then optional tokens before extension.
PN_HTML_RE = re.compile(
    r"^(?P<prefix>\d{1,2}(?:[A-Z]+)?)-(?P<num>\d+)(?:[A-Z0-9._-]*)?\.(?:html?|HTML?)$",
    re.IGNORECASE,
)

# Prefix splitter (digits + optional letters)
PREFIX_RE = re.compile(r'^(?P<digits>\d{1,2})(?P<suffix>[A-Z]+)?$', re.IGNORECASE)

# Global debug toggle (set from CLI)
DEBUG_DISCOVERY = False


# ---------------- Utils ----------------
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


def pause(enabled: bool = True, msg: str = "Press Enter to continue...") -> None:
    if not enabled or not sys.stdin.isatty():
        return
    try:
        input(msg)
    except EOFError:
        pass

def print_mitaza_header(subtitle: Optional[str] = None) -> None:
    art = (
        "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n"
        "   ((\n"
        "    ))        Mi Taza\n"
        "  | ~~~~ |]   a tool for running scripts to generate or update files. ☕\n"
        "  \\      /\n"
        "   `----'\n"
        "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
    )
    print(art)
    if subtitle:
        print(subtitle)
    print()

def banner(title: str, ch: str = "=", width: int = 80) -> str:
    line = ch * width
    return f"{line}\n{title}\n{line}"


def first_line_doc(path: Path, max_chars: int = 120) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    # Try docstring
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
    # Try leading comment header
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            s = s.lstrip("#").strip()
            if s:
                return (s[:max_chars] + "…") if len(s) > max_chars else s
    return ""


def _expand_globs(globs_str: str) -> List[str]:
    return [g.strip() for g in globs_str.split(",") if g.strip()]


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


def split_pn_rev_from_filename(p: Path) -> Tuple[str, str]:
    stem = p.stem
    parts = stem.split("_")
    pn, rev = "?", "?"
    if len(parts) >= 3 and parts[-1].lower() == "sch":
        pn, rev = parts[0], parts[1]
    elif len(parts) >= 2:
        pn, rev = parts[0], parts[1]
    return pn, rev


# ---------------- Discovery: Markdown ----------------
def find_sch_files(md_dir: Path, limit: int) -> List[Path]:
    files = sorted(md_dir.glob(SCH_GLOB_DEFAULT))
    return files[:limit] if limit and limit > 0 else files


def is_compiled_ds(name: str) -> bool:
    lname = name.lower()
    if lname.endswith("_sch.md") or lname.endswith("_man.md") or lname.endswith("_prompt.md") or lname.endswith("_feedback.md"):
        return False
    return bool(DS_RE.match(name))


def find_ds_files(md_dir: Path, limit: int) -> List[Path]:
    files = [p for p in sorted(md_dir.glob("*.md")) if is_compiled_ds(p.name)]
    return files[:limit] if limit and limit > 0 else files


# ---------------- Discovery: HTML ----------------
def _iter_html_files(root: Path):
    """Yield all .html/.htm files, case-insensitive, anywhere under root."""
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".html", ".htm"):
            yield p


def _norm_num(s: str) -> str:
    # '02' -> '2', '002' -> '2'; non-digits unchanged (uppercased elsewhere)
    return str(int(s)) if s.isdigit() else s


def _family_aliases(prefix: str) -> set:
    """
    Build acceptable family tokens for a prefix like '02A' or '09H' or '04'.
    - Always include full prefix (uppercased).
    - Include numeric root-only variants ('2', '02', '002') so 02A can live under 02/.
    - If suffix exists, include '2A' and '02A' as well.
    """
    m = PREFIX_RE.match(prefix)
    if not m:
        return {prefix.upper()}

    d = m.group('digits')           # e.g., '02'
    s = (m.group('suffix') or '').upper()  # e.g., 'A' or ''
    dn = _norm_num(d)               # '2'
    dn2 = dn.zfill(2)               # '02'
    dn3 = dn.zfill(3)               # '002'

    aliases = {prefix.upper(), d.upper(), dn, dn2, dn3}
    if s:
        aliases |= {dn + s, dn2 + s, (d + s).upper()}
    return aliases


def _folder_matches_family(name: str, aliases: set) -> bool:
    """
    Accept if folder name equals OR starts with any alias.
    This allows decorated folders like '02-archive', '09 (old)', etc.
    """
    u = name.upper()
    for token in aliases:
        if u == token or u.startswith(token) or u.startswith(token + '-') or u.startswith(token + '_') or u.startswith(token + ' '):
            return True
    return False


def find_part_pages(root: Path, limit: int, no_ancestor_check: bool = False) -> List[Path]:
    """
    Part webpages:
      - filename looks like '<prefix>-<digits>...(.htm|.html)'
      - by default, at least one ancestor folder matches the family:
          * matches full prefix (e.g., 04A) OR
          * matches numeric root variants (e.g., 2 / 02 / 002 for 02A)
          * allows decorated names like '02-archive'
      - if no_ancestor_check=True, folder constraint is skipped.
    """
    root = root.resolve()
    hits: List[Path] = []

    for p in sorted(_iter_html_files(root)):
        m = PN_HTML_RE.match(p.name)
        if not m:
            if DEBUG_DISCOVERY:
                print(f"[skip:regex] {p}")
            continue

        if no_ancestor_check:
            hits.append(p)
            continue

        fam_aliases = _family_aliases(m.group("prefix"))
        anc = p.parent.resolve()
        matched = False
        while True:
            if _folder_matches_family(anc.name, fam_aliases):
                matched = True
                break
            if anc == root or anc.parent == anc:
                break
            anc = anc.parent

        if matched:
            hits.append(p)
        elif DEBUG_DISCOVERY:
            print(f"[skip:ancestor] {p} (need ancestor starting with one of {sorted(fam_aliases)})")

    return hits[:limit] if limit and limit > 0 else hits


def find_all_html(root: Path, limit: int) -> List[Path]:
    files = sorted(_iter_html_files(root))
    return files[:limit] if limit and limit > 0 else files


# ---------------- Printing tables ----------------
def print_table_sch(files: List[Path]) -> None:
    if not files:
        print("No *_sch.md files found.")
        return
    print("\nDiscovered schematic markdown files:\n")
    print(f"{'#':>3}  {'PN':<12}  {'REV':<10}  PATH")
    print("-" * 70)
    for idx, f in enumerate(files, start=1):
        pn, rev = split_pn_rev_from_filename(f)
        print(f"{idx:>3}  {pn:<12}  {rev:<10}  {f}")


def print_table_ds(files: List[Path]) -> None:
    if not files:
        print("No compiled datasheets (PN_REV.md) found.")
        return
    print("\nDiscovered compiled datasheets:\n")
    print(f"{'#':>3}  {'PN':<12}  {'REV':<10}  PATH")
    print("-" * 70)
    for idx, f in enumerate(files, start=1):
        pn, rev = split_pn_rev_from_filename(f)
        print(f"{idx:>3}  {pn:<12}  {rev:<10}  {f}")


def print_table_html(label: str, files: List[Path]) -> None:
    if not files:
        print(f"No {label} HTML files found.")
        return
    print(f"\nDiscovered {label} HTML files:\n")
    print(f"{'#':>3}  {'FILE':<36}  PATH")
    print("-" * 90)
    for idx, f in enumerate(files, start=1):
        print(f"{idx:>3}  {f.name:<36}  {f}")


def print_scripts_table(items, scripts_dir: Path, pattern: str) -> None:
    print(f"\nScripts in {scripts_dir} matching {pattern}:\n")
    if not items:
        print("(none found)")
        return
    print(f"{'#':>3}  {'SCRIPT':<32}  DESCRIPTION")
    print("-" * 90)
    for i, (p, desc) in enumerate(items, start=1):
        print(f"{i:>3}  {p.name:<32}  {desc}")


# ---------------- Runner ----------------
def run_script(
    script_path: Path,
    arg: Optional[Path],
    script_args: List[str],
    clear_enabled: bool,
    pause_before_clear: bool,
    job_label: str = "",
    extra_positional: Optional[List[Path]] = None,
) -> int:
    # Do NOT clear before; show output, then wait to clear.
    if arg:
        with_arg = f"\nWITH INPUT: {arg}"
    elif extra_positional:
        with_arg = f"\nWITH INPUT: multiple files"
    else:
        with_arg = "\n(NO INPUT)"
    title = f"{job_label}\nRUNNING SCRIPT: {script_path.name}{with_arg}"
    print_mitaza_header("by Nolan Manteufel / miniPCB.com")
    print(banner(title, "=")); print()

    cmd: List[str] = [sys.executable, str(script_path)]
    manifest_path: Optional[str] = None

    # Add single arg if provided
    if arg:
        cmd.append(str(arg))

    # Add many positional args if provided (with Windows manifest fallback)
    if extra_positional:
        estimated = len(" ".join(cmd + [str(p) for p in extra_positional] + (script_args or [])))
        if sys.platform.startswith("win") and estimated > 7500:
            # write temp manifest and rely on the script supporting --paths-file
            try:
                tf = tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8")
                for p in extra_positional:
                    tf.write(str(p) + "\n")
                tf.close()
                manifest_path = tf.name
                cmd.extend(["--paths-file", manifest_path])
            except Exception as e:
                print(f"[ERR] Could not create manifest file: {e}")
                return 1
        else:
            cmd.extend([str(p) for p in extra_positional])

    if script_args:
        cmd.extend(script_args)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(script_path.parent),
            capture_output=False,
            text=False,
            check=False,
        )
        rc = proc.returncode
    except Exception as e:
        print(f"[ERR] Could not run {script_path.name}: {e}")
        rc = 1
    finally:
        if manifest_path:
            try:
                Path(manifest_path).unlink(missing_ok=True)  # py310+
            except Exception:
                pass

    print("\n" + banner(f"FINISHED: {script_path.name} (exit code {rc})\nOUTPUT TARGET: directory -> {script_path.parent}", "="))
    print()

    # Wait before clearing so output remains visible
    if pause_before_clear:
        try:
            input("Press Enter to clear the screen...")
        except EOFError:
            pass
    if clear_enabled:
        clear_screen(True)

    return rc


def run_batch(
    scripts_to_run: List[Path],
    inputs: List[Path],
    no_clear: bool,
    step_mode: bool,
    standalone: bool,
    script_args: List[str],
    label_prefix: str = "RUN",
    bulk_mode: bool = False,
) -> int:
    if not scripts_to_run:
        print("[ERR] No scripts selected to run.")
        return 4

    # Standalone/global scripts — single run, single pause/clear
    if standalone:
        total_jobs = len(scripts_to_run)
        for job, script_path in enumerate(scripts_to_run, start=1):
            job_label = f"{label_prefix} {job}/{total_jobs} — {script_path.name}"
            rc = run_script(
                script_path,
                arg=None,
                script_args=script_args,
                clear_enabled=not no_clear,
                pause_before_clear=not no_clear,
                job_label=job_label
            )
            if rc != 0:
                return rc
        if step_mode:
            pause(not no_clear, "All runs finished. Press Enter to return...")
        return 0

    # BULK MODE — single run, single pause/clear
    if bulk_mode and inputs:
        total_jobs = len(scripts_to_run)
        for job, script_path in enumerate(scripts_to_run, start=1):
            job_label = f"{label_prefix} {job}/{total_jobs} — {script_path.name} (bulk)"
            rc = run_script(
                script_path,
                arg=None,
                script_args=script_args,
                clear_enabled=not no_clear,
                pause_before_clear=not no_clear,
                job_label=job_label,
                extra_positional=inputs,
            )
            if rc != 0:
                return rc
        if step_mode:
            pause(not no_clear, "All runs finished. Press Enter to return...")
        return 0

    # PER-FILE RUNS — no pauses/clears between files; one at the very end
    total_jobs = len(scripts_to_run) * max(1, len(inputs))
    job = 0
    for script_path in scripts_to_run:
        if not inputs:
            # per-script run with no arguments: avoid mid-run pause/clear
            job += 1
            job_label = f"{label_prefix} {job}/{total_jobs} — {script_path.name}"
            rc = run_script(
                script_path,
                arg=None,
                script_args=script_args,
                clear_enabled=False,          # < no clear between runs
                pause_before_clear=False,     # < no pause between runs
                job_label=job_label
            )
            if rc != 0:
                return rc
            continue

        for i, arg in enumerate(inputs, start=1):
            job += 1
            job_label = f"{label_prefix} {job}/{total_jobs} — {script_path.name}"
            rc = run_script(
                script_path,
                arg=arg,
                script_args=script_args,
                clear_enabled=False,          # < no clear between files
                pause_before_clear=False,     # < no pause between files
                job_label=job_label
            )
            if rc != 0:
                return rc
            if step_mode and i != len(inputs):
                pause(not no_clear, "Press Enter for next input...")

    # Single end-of-batch pause/clear (consecutive mode)
    if not step_mode and not no_clear:
        pause(True, "All runs finished. Press Enter to clear the screen...")
        clear_screen(True)
    elif step_mode and not no_clear:
        # step_mode already paused between files; still give a final gentle pause/clear
        pause(True, "Batch complete. Press Enter to clear the screen...")
        clear_screen(True)

    return 0


# ---------------- CLI ----------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mi Taza — discover files (optional) and run scripts.")
    p.add_argument("--root", type=Path, default=Path.cwd(), help="Project root (default: CWD).")
    p.add_argument("--md-dir", type=Path, default=None, help="Override path to md/ folder (default: <root>/md)")

    # Optional direct target (skips Welcome). If omitted, Welcome shows.
    p.add_argument("--target", choices=["sch", "ds", "part", "html"], default=None,
                   help="Discovery target: sch=*_sch.md, ds=PN_REV.md, part=part webpages, html=all HTML")

    p.add_argument("--max", dest="max_items", type=int, default=99999, help="Limit how many items to display.")

    # Scripts discovery
    p.add_argument("--scripts-dir", type=Path, default=None, help="Directory with scripts (default: <root>/scripts).")
    p.add_argument("--scripts-glob", default=SCRIPTS_GLOB_DEFAULT,
                   help=f"Script globs, comma-separated (default: {SCRIPTS_GLOB_DEFAULT}).")

    # Selection & execution
    p.add_argument("--select", type=int, default=None, help="1-based selection index (non-interactive).")
    p.add_argument("--all", action="store_true", help="Select all discovered files (non-interactive).")
    p.add_argument("--no-clear", action="store_true", help="Disable clears and pauses.")
    p.add_argument("--bulk", action="store_true",
                   help="Run the chosen script once, passing ALL selected files as positional args (single process).")

    # Script choice fast path
    p.add_argument("--script-index", type=int, default=None, help="Pick N-th script (1-based).")
    p.add_argument("--script-name", type=str, default=None, help="Pick script by filename (exact→prefix→substring).")
    p.add_argument("--run-all-scripts", action="store_true", help="Run all discovered scripts.")

    # Standalone/global scripts
    p.add_argument("--standalone", action="store_true", help="Run chosen script(s) once with no file argument.")
    p.add_argument("--script-args", type=str, default="", help="Extra args passed to script(s) (quoted string).")

    # Batch convenience
    p.add_argument("--batch", action="store_true",
                   help="Shorthand for --all --run-all-scripts with no pauses/clears (per-file runs).")

    # Welcome control + discovery debug
    p.add_argument("--no-welcome", action="store_true", help="Skip the Welcome screen.")
    p.add_argument("--debug-discovery", action="store_true", help="Explain why HTML files are skipped.")
    p.add_argument("--no-ancestor-check", action="store_true",
                   help="List part-like HTML regardless of folder ancestry (debug/sanity).")

    return p.parse_args()


# ---------------- Welcome + selection helpers ----------------
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


def choose_script_by_name(scripts: List[Tuple[Path, str]], name: str) -> Optional[Path]:
    if not scripts or not name:
        return None
    for p, _ in scripts:
        if p.name == name:
            return p
    for p, _ in scripts:
        if p.name.startswith(name):
            return p
    for p, _ in scripts:
        if name in p.name:
            return p
    return None


def welcome_pick_target() -> Tuple[Optional[str], bool]:
    """Return (target or None, skip_discovery_flag)."""
    clear_screen(True)
    print_mitaza_header("by Nolan Manteufel / miniPCB.com")
    print(banner("Welcome"))
    print("Choose how to begin:\n")
    print("  1) Scan Markdown files")
    print("  2) Scan HTML files")
    print("  3) Proceed to scripts without scanning files")
    print()
    while True:
        c = input("Enter 1 / 2 / 3: ").strip()
        if c == "1":
            # Markdown sub-choice
            clear_screen(True)
            print_mitaza_header("by Nolan Manteufel / miniPCB.com")
            print(banner("Markdown scan — choose type"))
            print("  S) Schematic exports   (md/*_sch.md)")
            print("  D) Compiled datasheets (md/PN_REV.md)")
            print()
            sd = input("Enter S / D (Enter to cancel): ").strip().lower()
            if sd == "s":
                return "sch", False
            if sd == "d":
                return "ds", False
            return None, True
        elif c == "2":
            # HTML sub-choice
            clear_screen(True)
            print_mitaza_header("Script runner")
            print(banner("HTML scan — choose type"))
            print("  P) Part webpages (e.g., 04A/04A-010.html, 02/02A-00.html)")
            print("  A) All HTML files (site-wide)")
            print()
            ha = input("Enter P / A (Enter to cancel): ").strip().lower()
            if ha == "p":
                return "part", False
            if ha == "a":
                return "html", False
            return None, True
        elif c == "3":
            return None, True
        else:
            print("Please enter 1, 2, or 3.")


# ---------------- Main ----------------
def main() -> int:
    args = parse_args()

    # Debug toggle
    global DEBUG_DISCOVERY
    DEBUG_DISCOVERY = args.debug_discovery

    # Mode flags
    step_mode = False

    # Expand batch
    if args.batch:
        args.all = True
        args.run_all_scripts = True
        args.no_clear = True

    root: Path = args.root.resolve()
    scripts_dir: Path = (args.scripts_dir or (root / "scripts")).resolve()
    md_dir: Path = (args.md_dir or (root / "md")).resolve()

    if not root.exists():
        print(f"Root directory not found: {root}", file=sys.stderr)
        return 2

    # -------- Welcome screen (unless suppressed or --target provided)
    skip_discovery = False
    if not args.no_welcome and args.target is None and sys.stdin.isatty():
        chosen_target, skip_discovery = welcome_pick_target()
        args.target = chosen_target  # may be None if skipping discovery

    # -------- Discover per chosen/explicit target
    files: List[Path] = []
    if not skip_discovery and args.target:
        clear_screen(not args.no_clear)
        if args.target == "sch":
            files = find_sch_files(md_dir, args.max_items)
            print_table_sch(files)
        elif args.target == "ds":
            files = find_ds_files(md_dir, args.max_items)
            print_table_ds(files)
        elif args.target == "part":
            files = find_part_pages(root, args.max_items, no_ancestor_check=args.no_ancestor_check)
            print_table_html("part-page", files)
        else:  # html
            files = find_all_html(root, args.max_items)
            print_table_html("site", files)

    # -------- Build selection (ignored if --standalone; empty if skip_discovery)
    selected_indices: List[int] = []
    if not args.standalone and not skip_discovery and files:
        if args.all:
            selected_indices = list(range(1, len(files) + 1))
        elif args.select is not None:
            if 1 <= args.select <= len(files):
                selected_indices = [args.select]
            else:
                print(f"--select out of range (1..{len(files)}).", file=sys.stderr)
                return 3
        else:
            sel = choose_index_or_all(len(files), "\nSelect a file by number or 'A' for all (Enter to cancel): ")
            if sel is None:
                selected_indices = []
            elif sel == "all":
                selected_indices = list(range(1, len(files) + 1))
            else:
                selected_indices = [int(sel)]

    # -------- Discover scripts
    scripts = list_scripts(scripts_dir, args.scripts_glob)

    # -------- Non-interactive fast path
    script_args_list = args.script_args.split() if args.script_args else []
    scripts_to_run: List[Path] = []
    if args.run_all_scripts:
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
        inputs = [files[i - 1] for i in selected_indices] if (selected_indices and not args.standalone) else []
        return run_batch(
            scripts_to_run=scripts_to_run,
            inputs=inputs,
            no_clear=args.no_clear,
            step_mode=step_mode,
            standalone=args.standalone,
            script_args=script_args_list,
            label_prefix="RUN",
            bulk_mode=args.bulk,
        )

    # -------- Interactive loop (scripts hub)
    while True:
        clear_screen(not args.no_clear)

        # Selection summary
        if args.standalone:
            print("Mode: STANDALONE — scripts will run once with NO file input\n")
        else:
            if selected_indices and files:
                if len(selected_indices) == 1:
                    chosen = files[selected_indices[0] - 1]
                    print(f"Selected: {chosen}\n")
                else:
                    first = files[selected_indices[0] - 1]
                    print(f"Selected: {len(selected_indices)} items (first: {first})\n")
            else:
                print("Selected: (none)\n")

        print_scripts_table(scripts, scripts_dir, args.scripts_glob)

        mode_label = "Step-through" if step_mode else "Consecutive"
        menu = f"""
Options:
  [#]  Run script on {"(no inputs — standalone)" if args.standalone else f"{len(selected_indices) or 0} selected item(s)"}
  [B]  Bulk run (single process; pass all selected files)
  [G]  Run script (global / no file input)
  [W]  Welcome — choose scan again (Markdown, HTML, or skip)
  [T]  Toggle per-file mode (currently: {mode_label})
  [R]  Reselect item(s)
  [C]  Change scripts dir
  [O]  Open scripts dir
  [Q]  Quit
""".strip()
        print(menu)

        choice = input("Enter choice (number/B/G/W/T/R/C/O/Q): ").strip().lower()

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(scripts):
                script_path = scripts[idx - 1][0]
                if args.standalone:
                    rc = run_batch([script_path], [], args.no_clear, step_mode, True, script_args_list, "RUN")
                else:
                    inputs = [files[i - 1] for i in selected_indices] if selected_indices else []
                    rc = run_batch(
                        [script_path], inputs, args.no_clear, step_mode,
                        False, script_args_list, "RUN", bulk_mode=False
                    )
                if rc != 0:
                    return rc
                scripts = list_scripts(scripts_dir, args.scripts_glob)
                continue
            print(f"Number out of range. Enter 1..{len(scripts)}.")
            pause(not args.no_clear)
            continue

        if choice in ("q", ""):
            return 0
        elif choice == "b":
            if args.standalone:
                print("Bulk mode not applicable in standalone; pick [#] or [G].")
                pause(not args.no_clear); continue
            if not selected_indices:
                print("No items selected. Use [R] to select files first.")
                pause(not args.no_clear); continue
            pick = input("Enter script number to bulk run: ").strip()
            if pick.isdigit():
                sidx = int(pick)
                if 1 <= sidx <= len(scripts):
                    inputs = [files[i - 1] for i in selected_indices]
                    rc = run_batch(
                        scripts_to_run=[scripts[sidx - 1][0]],
                        inputs=inputs,
                        no_clear=args.no_clear,
                        step_mode=step_mode,
                        standalone=False,
                        script_args=script_args_list,
                        label_prefix="RUN",
                        bulk_mode=True,
                    )
                    if rc != 0:
                        return rc
                else:
                    print("Invalid script number."); pause(not args.no_clear)
            else:
                print("Cancelled."); pause(not args.no_clear)
        elif choice == "g":
            if not scripts:
                print("(no scripts found)")
                pause(not args.no_clear)
                continue
            pick = input("Enter script number to run globally (no file input): ").strip()
            if pick.isdigit():
                sidx = int(pick)
                if 1 <= sidx <= len(scripts):
                    rc = run_batch([scripts[sidx - 1][0]], [], args.no_clear, step_mode, True, script_args_list, "RUN")
                    if rc != 0:
                        return rc
                else:
                    print("Invalid script number.")
                    pause(not args.no_clear)
            else:
                print("Cancelled.")
                pause(not args.no_clear)
        elif choice == "w":
            # Re-enter Welcome flow
            t, skip = welcome_pick_target()
            args.target = t
            skip_discovery = skip
            files = []
            selected_indices = []
            if not skip_discovery and args.target:
                clear_screen(not args.no_clear)
                if args.target == "sch":
                    files = find_sch_files(md_dir, args.max_items); print_table_sch(files)
                elif args.target == "ds":
                    files = find_ds_files(md_dir, args.max_items); print_table_ds(files)
                elif args.target == "part":
                    files = find_part_pages(root, args.max_items, no_ancestor_check=args.no_ancestor_check); print_table_html("part-page", files)
                else:
                    files = find_all_html(root, args.max_items); print_table_html("site", files)
                sel = choose_index_or_all(len(files), "\nSelect a file by number or 'A' for all (Enter to cancel): ")
                if sel == "all":
                    selected_indices = list(range(1, len(files) + 1))
                elif isinstance(sel, int):
                    selected_indices = [sel]
        elif choice == "t":
            step_mode = not step_mode
        elif choice == "r":
            if skip_discovery or not args.target:
                print("No discovery list loaded. Use [W] to scan first.")
                pause(not args.no_clear)
                continue
            # Reprint current list for reselection
            if args.target in ("sch", "ds"):
                print_table_sch(files) if args.target == "sch" else print_table_ds(files)
            else:
                print_table_html("part-page" if args.target == "part" else "site", files)
            sel = choose_index_or_all(len(files), "\nSelect a file by number or 'A' for all (Enter to cancel): ")
            if sel == "all":
                selected_indices = list(range(1, len(files) + 1))
            elif isinstance(sel, int):
                selected_indices = [sel]
        elif choice == "c":
            new_dir = input("Enter path to scripts directory (or press Enter to keep current): ").strip()
            if new_dir:
                scripts_dir = Path(new_dir).expanduser().resolve()
                print(f"Scripts directory set to: {scripts_dir}")
                pause(not args.no_clear)
            scripts = list_scripts(scripts_dir, args.scripts_glob)
        elif choice == "o":
            print(f"Opening folder: {scripts_dir}")
            open_folder(scripts_dir)
            pause(not args.no_clear)
        else:
            print("Unrecognized option. Choose a script number, B, G, W, T, R, C, O, or Q.")
            pause(not args.no_clear)


if __name__ == "__main__":
    sys.exit(main())
