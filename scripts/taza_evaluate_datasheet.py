#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate feedback on a datasheet using an LLM.

taza_evaluate.py

Evaluate PN_REV.md and generate PN_REV_feedback.md using an LLM.
- Always overwrites output (no --force needed).
- Robust result extraction from OpenAI Responses or Chat API objects.
- Verbose mode (--verbose) and also print to stdout (--stdout).

Usage:
  python taza_evaluate.py path/to/PN_REV.md
  python taza_evaluate.py path/to/PN_REV_sch.md --verbose --stdout
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional, Set, Tuple

try:
    from openai import OpenAI  # pip install openai
except ImportError:
    print("Missing dependency: pip install openai", file=sys.stderr)
    sys.exit(1)

# Approved REF DES prefixes
APPROVED_REF_PREFIXES = [
    "A","AR","AT","B","BT","C","CB","CP","CR","D","DC","DL","DS","E","EQ","F","FL","G","H",
    "HP","HR","HS","HT","HW","HX","J","K","L","LED","LS","M","MG","MK","MP","MT","P","PS",
    "Q","R","RT","S","T","TB","TP","U","VR","W","WT","X","Y"
]
_REF_PREFIX_ALT = "|".join(sorted(APPROVED_REF_PREFIXES, key=len, reverse=True))
APPROVED_REFDES_RE = re.compile(rf"\b(?:{_REF_PREFIX_ALT})\d{{1,6}}\b", re.IGNORECASE)

NET_RE = re.compile(
    r"\bN\$[A-Za-z0-9_]+\b|\bGND\b|\bVIN\b|\bVOUT\b|\bVCC\b|\bVDD\b|\bVSS\b|\bREF\b|\bV\+|\bV-",
    re.IGNORECASE,
)

SCH_RE = re.compile(r'^(?P<pn>[^_/\\]+)_(?P<rev>[^_/\\]+)_(?:sch|shc)\.md$', re.IGNORECASE)
MAN_RE = re.compile(r'^(?P<pn>[^_/\\]+)_(?P<rev>[^_/\\]+)_man\.md$', re.IGNORECASE)
DS_RE  = re.compile(r'^(?P<pn>[^_/\\]+)_(?P<rev>[^_/\\]+)\.md$', re.IGNORECASE)

def read_text(p: Optional[Path]) -> str:
    if not p:
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""

def extract_identifiers(*texts: str) -> Tuple[Set[str], Set[str]]:
    refdes: Set[str] = set()
    nets: Set[str] = set()
    for t in texts:
        if not t:
            continue
        for m in APPROVED_REFDES_RE.finditer(t):
            refdes.add(m.group(0).upper())
        for m in NET_RE.finditer(t):
            nets.add(m.group(0))
    return refdes, nets

def derive_bundle(input_path: Path):
    name = input_path.name
    m_ds = DS_RE.match(name)
    m_sch = SCH_RE.match(name)
    m_man = MAN_RE.match(name)

    if m_ds:
        pn, rev = m_ds.group("pn"), m_ds.group("rev")
        ds = input_path
        sch = input_path.parent / f"{pn}_{rev}_sch.md"
        man = input_path.parent / f"{pn}_{rev}_man.md"
        return ds, (sch if sch.exists() else None), (man if man.exists() else None), pn, rev

    if m_sch:
        pn, rev = m_sch.group("pn"), m_sch.group("rev")
        ds = input_path.parent / f"{pn}_{rev}.md"
        sch = input_path
        man = input_path.parent / f"{pn}_{rev}_man.md"
        return ds, sch, (man if man.exists() else None), pn, rev

    if m_man:
        pn, rev = m_man.group("pn"), m_man.group("rev")
        ds = input_path.parent / f"{pn}_{rev}.md"
        man = input_path
        sch = input_path.parent / f"{pn}_{rev}_sch.md"
        return ds, (sch if sch.exists() else None), man, pn, rev

    raise ValueError(f"Could not parse PN/REV from filename: {name}")

def build_prompt(pn, rev, datasheet_md, sch_md, man_md, refdes_allowed, nets_allowed):
    refdes_list = ", ".join(sorted(refdes_allowed)) or "(none)"
    nets_list = ", ".join(sorted(nets_allowed)) or "(none)"
    return f"""
You are a meticulous technical editor and senior analog design reviewer.
Your task: **review a compiled datasheet** and produce a structured list of **issues** with fixes.

Target:
- PN: {pn}
- REV: {rev}

Authoritative identifiers (from schematic export):
- Allowed refdes: {refdes_list}
- Allowed nets: {nets_list}

Deliverable (Markdown only):
- Begin with "# {pn} {rev} — Feedback".
- Provide a summary paragraph of overall quality.
- Then a table with columns:
  | # | Severity | Category | Location | Finding | Suggested Fix | Confidence |
- After the table, add a "Checks Performed" list.

Rules:
- **Do not** invent new component IDs beyond the net and part lists.
- Flag any refdes that appears in the datasheet but is not in Allowed lists.
- Call out obvious typos and unit/style problems.

Context — DATASHEET:
```
{datasheet_md}
```

Context — SCHEMATIC_MD:
```
{sch_md}
```

Context — MANUAL_MD:
```
{man_md}
```
""".strip()

def get_output_text(resp) -> str:
    text = getattr(resp, "output_text", None)
    if text:
        return text
    try:
        out = getattr(resp, "output", None)
        if isinstance(out, list) and out:
            blocks = out[0].get("content") if isinstance(out[0], dict) else None
            if isinstance(blocks, list):
                for b in blocks:
                    if b.get("type") in ("text", "output_text"):
                        return b.get("text") or b.get("content") or ""
    except Exception:
        pass
    try:
        choices = getattr(resp, "choices", None)
        if choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else getattr(choices[0], "message", None)
            if msg:
                return msg.get("content") or ""
    except Exception:
        pass
    return ""

def main():
    ap = argparse.ArgumentParser(description="Evaluate PN_REV.md and generate PN_REV_feedback.md using an LLM.")
    ap.add_argument("path", type=Path, help="Path to PN_REV.md or PN_REV_sch.md / PN_REV_man.md")
    ap.add_argument("--datasheet", type=Path, default=None, help="Explicit path to datasheet markdown")
    ap.add_argument("--sch", type=Path, default=None, help="Explicit path to schematic markdown")
    ap.add_argument("--man", type=Path, default=None, help="Explicit path to manual markdown")
    ap.add_argument("--model", default="gpt-4o", help="OpenAI model (e.g., gpt-4o)")
    ap.add_argument("--temperature", type=float, default=0.1)
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--stdout", action="store_true", help="Also print feedback to stdout")
    ap.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = ap.parse_args()

    # Resolve explicit or inferred bundle
    if args.datasheet:
        ds_path = args.datasheet
        m = re.match(r'^(?P<pn>[^_/\\]+)_(?P<rev>[^_/\\]+)\.md$', ds_path.name, re.IGNORECASE)
        if m:
            pn, rev = m.group("pn"), m.group("rev")
        else:
            pn, rev = "UNKNOWN_PN", "UNKNOWN_REV"
        sch_path = args.sch
        man_path = args.man
    else:
        ds_path, sch_path, man_path, pn, rev = derive_bundle(args.path)

    if not ds_path or not ds_path.exists():
        print(f"ERROR: Datasheet not found: {ds_path}", file=sys.stderr)
        sys.exit(2)

    datasheet_md = read_text(ds_path)
    sch_md = read_text(sch_path)
    man_md = read_text(man_path)

    refdes_allowed, nets_allowed = extract_identifiers(sch_md)
    if not refdes_allowed:
        refdes_allowed, _ = extract_identifiers(datasheet_md)

    if args.verbose:
        print(f"[VERBOSE] PN={pn} REV={rev}")
        print(f"[VERBOSE] Datasheet: {ds_path} ({len(datasheet_md)} chars)")
        print(f"[VERBOSE] Schematic: {sch_path if sch_path else '(missing)'} ({len(sch_md)} chars)")
        print(f"[VERBOSE] Manual   : {man_path if man_path else '(missing)'} ({len(man_md)} chars)")
        print(f"[VERBOSE] Allowed REF DES: {len(refdes_allowed)} | Allowed nets: {len(nets_allowed)}")

    prompt = build_prompt(pn, rev, datasheet_md, sch_md, man_md, refdes_allowed, nets_allowed)

    client = OpenAI()
    feedback_md = ""
    last_err = None
    for _ in range(max(1, args.retries)):
        try:
            resp = client.responses.create(
                model=args.model,
                input=prompt,
                temperature=args.temperature,
                max_output_tokens=args.max_tokens,
                timeout=args.timeout,
            )
            feedback_md = get_output_text(resp).strip()
            if feedback_md:
                break
            last_err = RuntimeError("Empty response")
        except Exception as e:
            last_err = e
            continue

    if not feedback_md:
        print(f"ERROR: generation failed or empty output: {last_err}", file=sys.stderr)
        sys.exit(3)

    out_path = ds_path.with_name(ds_path.name.replace(".md", "_feedback.md"))
    out_path.write_text(feedback_md, encoding='utf-8')
    if args.stdout:
        print(feedback_md)
    print(f"✅ Wrote: {out_path}")

if __name__ == "__main__":
    main()
