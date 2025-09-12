#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tava_generate_prompt.py

Generate a structured AI prompt markdown file (PN_REV_prompt.md) from a schematic
markdown export (PN_REV_sch.md). Designed to guide an AI to produce analysis
plans/reports (EPSA, WCCA, FMEA, SI, etc.) and commentary.

Key behavior:
- By default, embeds FULL _sch.md and (if present) FULL _man.md verbatim.
- To avoid duplication, Quick-Scan summary tables are OMITTED by default when
  the corresponding full source is embedded.
- Use --summary to include Quick-Scan tables (still deduplicated if requested).

USAGE:
  python tava_generate_prompt.py path/to/PN_REV_sch.md

OPTIONS:
  -o, --outdir DIR         Output directory (default: alongside input)
  --max-netlist N          Max netlist rows in summary (default: -1 for FULL; 0 = exclude)
  --max-partlist N         Max partlist rows in summary (default: -1 for FULL; 0 = exclude)
  --no-pinout              Do not include pinout section in summary
  --dedupe-tables          Remove duplicate DATA rows in derived tables (keeps header)
  --summary                Include Quick-Scan summaries even if full sources are embedded
  --force                  Overwrite an existing *_prompt.md
  --title TITLE            Override the prompt title in the output
  --add-note TEXT          Append an extra NOTE block (repeatable)
  --no-full-sch            Do NOT embed full _sch.md content
  --no-man                 Do NOT embed _man.md content
  --man PATH               Explicit path to manual commentary markdown (overrides auto-detect)

CONVENTIONS:
  - Input filename: PN_REV_sch.md (also accepts *_shc.md)
  - Output filename: PN_REV_prompt.md
"""
import argparse
import os
import re
import sys
import glob
from typing import Dict, List, Tuple

HEADING_RE = re.compile(r'^(#+)\s+(.*)\s*$', re.IGNORECASE)
PIPE_TABLE_LINE_RE = re.compile(r'^\s*\|.*\|\s*$', re.IGNORECASE)
MD_CODE_FENCE = "```"

DEFAULT_MAX_NETLIST = -1
DEFAULT_MAX_PARTLIST = -1

TESTBASE_TEST_TEMPLATE_JSON = """{
  "test_name": "Short, human-friendly title (e.g., “Op-amp offset vs. temperature”).",
  "test_no": "Unique test ID (e.g., 001).",
  "last_test_no": "Related/previous test ID (if applicable).",
  "single_or_batch": "single capable or batch only",
  "purpose": "What question this test answers and why it matters.",
  "scope": "Boundaries and conditions: in-scope subsystems, environments, ranges.",
  "setup": "Equipment/fixtures, DUT configuration, calibration steps, references.",
  "procedure": "Numbered, step-by-step instructions with timings and checkpoints.",
  "measurement": "Exactly what to record (signal names, units, sample rate, instruments/channels).",
  "acceptancecriteria": "Quantitative pass/fail thresholds with formulas or limits (include tolerances).",
  "conclusion": "Result summary (Pass/Fail) and brief rationale; note anomalies or follow-ups."
}"""

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def try_read_text(path: str) -> str:
    try:
        return read_text(path)
    except Exception:
        return ""

def write_text(path: str, text: str, force: bool = False) -> None:
    if os.path.exists(path) and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {path} (rerun without --no-clobber)")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def split_sections(md: str) -> Dict[str, List[str]]:
    """
    Split markdown into sections keyed by normalized heading text.
    Returns dict: { "circuit identification": [lines...], ... }
    """
    lines = md.splitlines()
    sections: Dict[str, List[str]] = {}
    current_key = "_preamble"
    sections[current_key] = []
    for line in lines:
        m = HEADING_RE.match(line)
        if m:
            heading_text = m.group(2).strip().lower()
            current_key = heading_text
            sections.setdefault(current_key, [])
        sections[current_key].append(line)
    return sections

def extract_table_lines(section_lines: List[str]) -> List[str]:
    """
    Extract contiguous markdown pipe-table lines from a section.
    Returns a list of pipe-table lines (including header separator), preserving order.
    """
    tables: List[str] = []
    started = False
    for line in section_lines:
        if PIPE_TABLE_LINE_RE.match(line):
            tables.append(line.rstrip())
            started = True
        else:
            if started:
                break
    return tables

def is_separator_row(row: str) -> bool:
    r = row.replace(' ', '')
    # Typical separator like: |-----|:----:|---|
    return r.startswith('|') and set(r) <= set('|-:')

def dedupe_table_lines(table_lines: List[str]) -> List[str]:
    """Deduplicate DATA rows only (preserve header + separator order)."""
    if not table_lines:
        return table_lines

    # Identify header and separator rows.
    header = []
    sep = []
    data = []

    # If second row looks like a separator, treat first as header
    if len(table_lines) >= 2 and is_separator_row(table_lines[1]):
        header = [table_lines[0]]
        sep = [table_lines[1]]
        data = table_lines[2:]
    else:
        header = [table_lines[0]]
        data = table_lines[1:]

    seen = set()
    deduped = []
    for row in data:
        key = row.strip()
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    return header + sep + deduped if sep else header + deduped

def trim_table_rows(table_lines: List[str], max_rows: int) -> List[str]:
    """
    Keep header, separator, and first max_rows of data.
    - max_rows < 0: keep ALL rows (no truncation)
    - max_rows == 0: exclude table entirely
    """
    if not table_lines:
        return []
    if max_rows < 0:
        return table_lines
    if max_rows == 0:
        return []

    header_idx = 0
    sep_idx = 1 if len(table_lines) > 1 and is_separator_row(table_lines[1]) else -1

    if sep_idx == -1:
        # no clear separator; keep up to max_rows lines (including header line)
        header = table_lines[:1]
        data = table_lines[1:1 + max_rows] if max_rows > 0 else []
        return header + data

    header = table_lines[header_idx:header_idx+1]
    sep = table_lines[sep_idx:sep_idx+1]
    data = table_lines[sep_idx+1:]
    if max_rows > 0:
        data = data[:max_rows]
    return header + sep + data

def derive_pn_rev_from_filename(path: str) -> Tuple[str, str]:
    """
    From 'PN_REV_sch.md' (or *_shc.md), return (PN, REV).
    Example: '04A-005_A1-01_sch.md' => ('04A-005', 'A1-01')
    """
    base = os.path.basename(path)
    base = re.sub(r'(_sch|_shc)\.md$', '', base, flags=re.IGNORECASE)
    parts = base.split('_')
    if len(parts) < 2:
        raise ValueError(f"Expected 'PN_REV_sch.md' naming. Got: {os.path.basename(path)}")
    pn = "_".join(parts[:-1]) if len(parts) > 2 else parts[0]
    rev = parts[-1]
    return pn, rev

def find_first_table_under_heading(sections: Dict[str, List[str]], heading_candidates: List[str]) -> List[str]:
    for h in heading_candidates:
        if h in sections:
            t = extract_table_lines(sections[h])
            if t:
                return t
    return []

def safe_join(lines: List[str]) -> str:
    return "\n".join(lines).rstrip() + ("\n" if lines else "")

def md_collapsible(title: str, inner_md: str) -> str:
    if not inner_md.strip():
        return ""
    return f"""<details>
<summary>{title}</summary>

{inner_md.rstrip()}
</details>
"""

def md_collapsible_verbatim(title: str, body_md: str) -> str:
    if not body_md.strip():
        return ""
    return f"""<details>
<summary>{title}</summary>

```markdown
{body_md.rstrip()}
```
</details>
"""

def build_prompt_md(
    pn: str,
    rev: str,
    title_override: str,
    include_summary: bool,
    circuit_id_table: List[str],
    netlist_table: List[str],
    partlist_table: List[str],
    pinout_table: List[str],
    extra_notes: List[str],
    full_sch_md: str,
    full_man_md: str,
    include_full_sch: bool,
    include_full_man: bool
) -> str:
    prompt_title = title_override or f"{pn} {rev} — Analysis Plans & Reports Prompt"

    # Optional Quick-Scan (only if include_summary=True)
    quick_scan_blocks = []
    if include_summary:
        if circuit_id_table:
            quick_scan_blocks.append(md_collapsible("Circuit Identification (from schematic export)", safe_join(circuit_id_table)))
        if partlist_table:
            quick_scan_blocks.append(md_collapsible("Partlist (subset)", safe_join(partlist_table)))
        if netlist_table:
            quick_scan_blocks.append(md_collapsible("Netlist (subset)", safe_join(netlist_table)))
        if pinout_table:
            quick_scan_blocks.append(md_collapsible("Pinout (if available)", safe_join(pinout_table)))
    quick_scan_md = ("\n".join(quick_scan_blocks).strip()) if quick_scan_blocks else ""

    extra_notes_block = ""
    if extra_notes:
        extra_notes_block = "\n".join(f"> NOTE: {n}" for n in extra_notes) + "\n"

    testbase_json_block = f"""```json
{TESTBASE_TEST_TEMPLATE_JSON}
```"""

    full_blocks = []
    if include_full_sch and full_sch_md.strip():
        full_blocks.append(md_collapsible_verbatim("Full Schematic Markdown (verbatim)", full_sch_md))
    if include_full_man and full_man_md.strip():
        full_blocks.append(md_collapsible_verbatim("Manual Commentary (verbatim)", full_man_md))
    full_sources_md = ("\n\n".join(full_blocks).strip()) if full_blocks else ""

    # Assemble document—no duplicated content sections.
    parts = []
    parts.append(f"# {prompt_title}\n")
    parts.append(f"You are an expert electronics engineer and reliability analyst. Using the provided circuit context, generate the following **deliverables** for Part Number **{pn}**, Revision **{rev}**:\n")
    parts.append("""## Deliverables
1. **Automatic Commentary** (`*_aut.md`): Clear, structured narrative covering Purpose & Scope, Key Design Points, Circuit Description, Circuit Theory, Design Tradeoffs, and Practical Considerations.
2. **EPSA** (Electrical Parts Stress Analysis):
   - **Plan** (`*_epsa_plan.md`): Assumptions, required data, methodology, equations, test matrix, and acceptance criteria.
   - **Report** (`*_epsa.md`): Completed analysis with tables, calculations, and conclusions.
3. **WCCA** (Worst-Case Circuit Analysis):
   - **Plan** (`*_wcca_plan.md`): Assumptions, corners, parameter ranges, models, and methodology.
   - **Report** (`*_wcca.md`): Calculations and pass/fail determinations per function.
4. **FMEA** (Failure Modes and Effects Analysis):
   - **Plan** (`*_fmea_plan.md`)
   - **Report** (`*_fmea.md`): Itemized failure modes, effects, causes, detection, mitigations; include severity/occurrence/detection ratings and RPN.
5. **Signal Integrity (SI)**:
   - **Plan** (`*_si_plan.md`)
   - **Report** (`*_si.md`): Layer stack-up assumptions, controlled impedance traces (if any), terminations, reflections, crosstalk, and timing margins.
6. **Master Document** (`*_master.md`): Concise executive overview linking to all above sections with a one-page summary table (artifacts, versions, and dates).
""")
    if quick_scan_md:
        parts.append("\n## Inputs & Context (Quick-Scan)\nUse the following as ground truth context. Do not invent part numbers or nets not present unless explicitly stated as an assumption.\n\n")
        parts.append(quick_scan_md + "\n")

    if full_sources_md:
        parts.append("\n## Full Source Context (Verbatim)\nThe following sections include the **complete** schematic export and manual commentary to ensure fidelity and traceability.\n\n")
        parts.append(full_sources_md + "\n")

    parts.append("\n## TestBASE Test Item Template (for any required experimental verification)\nUse/extend the following JSON object for individual test items (Plan → Report mapping). Provide at least one example filled-out test for each critical function or risk area you identify.\n\n")
    parts.append(testbase_json_block + "\n")

    parts.append(f"""## Output Requirements
- Produce **each deliverable** as a separate Markdown section in your response, prefixed with a level-1 heading containing the target filename in backticks. Example:

# `{pn}_{rev}_epsa_plan.md`
(...content...)

- Include **FULL tables** (no truncation). If a table is extremely large, split across multiple tables or provide an attached CSV/JSON in addition to the Markdown.
- Include a **TODO** list per deliverable for any data you need from CAD (e.g., exact stackup, trace widths, thermal limits).
""")

    parts.append("""## Safety & Practical Notes
- If the circuit interacts with power electronics or high voltages/currents, include a **Safety Considerations** subsection.
- If any datasheet-dependent parameter is required (e.g., SOA, temp coefficients), mention the parameter and where it would be sourced.
""")

    if extra_notes_block:
        parts.append("\n" + extra_notes_block)

    return "".join(parts)

def main():
    ap = argparse.ArgumentParser(description="Generate PN_REV_prompt.md from PN_REV_sch.md")
    ap.add_argument("input", help="Path to PN_REV_sch.md (accepts glob; also accepts *_shc.md)")
    ap.add_argument("-o", "--outdir", default=None, help="Output directory (default: alongside input)")
    ap.add_argument("--max-netlist", type=int, default=DEFAULT_MAX_NETLIST, help="Max rows from Netlist table in summary (0 = exclude)")
    ap.add_argument("--max-partlist", type=int, default=DEFAULT_MAX_PARTLIST, help="Max rows from Partlist table in summary (0 = exclude)")
    ap.add_argument("--no-pinout", action="store_true", help="Do not include pinout section in summary")
    ap.add_argument("--dedupe-tables", action="store_true", help="Remove duplicate DATA rows in derived tables (keeps header)")
    ap.add_argument("--summary", action="store_true", help="Include Quick-Scan summaries even if full sources are embedded")
    ap.add_argument("--force", action="store_true", default=True, help="Overwrite existing output file (default: on). Use --no-clobber to prevent overwriting.")
    ap.add_argument("--no-clobber", action="store_true", help="Do not overwrite if file exists")
    ap.add_argument("--title", default=None, help="Override prompt title")
    ap.add_argument("--add-note", action="append", default=[], help="Append an extra NOTE block (repeatable)")
    ap.add_argument("--no-full-sch", action="store_true", help="Do NOT embed full _sch.md content")
    ap.add_argument("--no-man", action="store_true", help="Do NOT embed _man.md content")
    ap.add_argument("--man", default=None, help="Explicit path to manual commentary markdown (overrides auto-detect)")
    args = ap.parse_args()

    # If user requested no-clobber, turn off force
    if getattr(args, "no_clobber", False):
        args.force = False


    candidates = glob.glob(args.input)
    if not candidates:
        print(f"ERROR: No files matched: {args.input}", file=sys.stderr)
        sys.exit(2)
    if len(candidates) > 1:
        print("ERROR: Multiple files matched. Please provide a single path or a more specific glob:", file=sys.stderr)
        for c in candidates:
            print(f" - {c}", file=sys.stderr)
        sys.exit(2)
    in_path = candidates[0]

    if not os.path.isfile(in_path):
        print(f"ERROR: File not found: {in_path}", file=sys.stderr)
        sys.exit(2)

    try:
        pn, rev = derive_pn_rev_from_filename(in_path)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    outdir = args.outdir or os.path.dirname(os.path.abspath(in_path))
    out_base = f"{pn}_{rev}_prompt.md"
    out_path = os.path.join(outdir, out_base)

    # Read and parse the schematic markdown
    full_sch_md = read_text(in_path)
    sections = split_sections(full_sch_md)

    # Extract tables for optional Quick-Scan
    circuit_id = find_first_table_under_heading(
        sections, ["circuit identification", "core identification", "identification"]
    )

    netlist = []
    if args.max_netlist != 0:
        netlist_raw = find_first_table_under_heading(
            sections, ["netlist (schematic)", "netlist", "schematic netlist"]
        )
        netlist = netlist_raw
        if args.dedupe_tables:
            netlist = dedupe_table_lines(netlist)
        netlist = trim_table_rows(netlist, args.max_netlist)

    partlist = []
    if args.max_partlist != 0:
        partlist_raw = find_first_table_under_heading(
            sections, ["partlist", "bom", "bill of materials"]
        )
        partlist = partlist_raw
        if args.dedupe_tables:
            partlist = dedupe_table_lines(partlist)
        partlist = trim_table_rows(partlist, args.max_partlist)

    pinout = []
    if not args.no_pinout:
        pinout = find_first_table_under_heading(
            sections, ["pinout", "pinout for p1", "pin labels", "connector pinout"]
        )
        if args.dedupe_tables:
            pinout = dedupe_table_lines(pinout)

    # Manual commentary path / content
    full_man_md = ""
    include_full_man = not args.no_man
    if include_full_man:
        man_path = args.man
        if man_path is None:
            # Auto-detect {pn}_{rev}_man.md in same folder
            guess = os.path.join(os.path.dirname(os.path.abspath(in_path)), f"{pn}_{rev}_man.md")
            if os.path.isfile(guess):
                man_path = guess
        if man_path:
            full_man_md = try_read_text(man_path)
            if args.man is not None and not full_man_md.strip():
                print(f"WARNING: Could not read manual commentary file: {man_path}", file=sys.stderr)

    prompt_md = build_prompt_md(
        pn=pn,
        rev=rev,
        title_override=args.title,
        include_summary=args.summary,  # only include summaries when explicitly requested
        circuit_id_table=circuit_id,
        netlist_table=netlist,
        partlist_table=partlist,
        pinout_table=pinout,
        extra_notes=args.add_note,
        full_sch_md=full_sch_md,
        full_man_md=full_man_md,
        include_full_sch=(not args.no_full_sch),
        include_full_man=include_full_man
    )

    os.makedirs(outdir, exist_ok=True)
    write_text(out_path, prompt_md, force=args.force)
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main()
