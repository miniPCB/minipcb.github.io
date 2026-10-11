#!/usr/bin/env python3
r"""
minipcb_kicad_sch_md.py

Standalone miniPCB Markdown exporter for KiCad schematics.

Strategy
--------
1. Ask KiCad to export a kicadxml netlist. This gives us authoritative
   connectivity, references, values, custom fields, pin functions, etc.
2. Read the .kicad_sch file directly only for graphical text such as the
   miniPCB "NOTES:" block.
3. Generate a Markdown document patterned after 0_export_sch_md2.ulp.

Designed for KiCad 8/9/10 style CLI:
    kicad-cli sch export netlist --format kicadxml ...

No third-party Python packages are required.

Example
-------
    python minipcb_kicad_sch_md.py my_design.kicad_sch

Optional:
    python minipcb_kicad_sch_md.py my_design.kicad_sch ^
        --output C:\Repos\KiCad\md ^
        --mirror C:\Repos\minipcb.github.io\md

miniPCB conventions expected
----------------------------
Special schematic symbols / components:
    PCB1
        PART_NUMBER
        REVISION
        TITLE

    DWG1
        DIMENSIONS
        PART_WEBPAGE
        DATASHEET
        ENG_NOTES
        TEST_SCRIPT
        GERBERS
        LTSPICE
        CAD_SOURCE
        VID_DESIGN_REVIEW
        VID_BUILD
        VID_TEST
        VID_DEMO
        VID_TUTORIAL

    SHEET1
        REV_1 / DATE_1 / DESCRIPTION_1
        REV_2 / DATE_2 / DESCRIPTION_2
        REV_3 / DATE_3 / DESCRIPTION_3
        REVA_INSTRUCTABLES
        REVB_INSTRUCTABLES
        REVC_INSTRUCTABLES

    P1
        pin1, pin2, ...
        NOTE1, NOTE2, ...

    TPx
        FUNCTION

Normal components may also contain:
        FUNCTION

Notes
-----
KiCad user-defined symbol properties are exported by kicadxml as <field>
elements. This script treats property names case-insensitively.

The generated netlist uses KiCad's exported connectivity. "Pad" is the
schematic pin number, since the schematic/netlist does not inherently know
the final PCB pad number in every symbol/footprint arrangement.

Revision
--------
10OCT2026 Initial KiCad Python exporter based on miniPCB EAGLE
0_export_sch_md2.ulp behavior.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCRIPT_REVISION_DATE = "20261010"

TARGET_CONN = "P1"
PCB_PART = "PCB1"
DWG_PART = "DWG1"
SHEET_PART = "SHEET1"

GITHUB_BASE = "https://github.com/miniPCB/minipcb.github.io/blob/main/"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Component:
    ref: str
    value: str = ""
    footprint: str = ""
    lib: str = ""
    part: str = ""
    fields: Dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str = "") -> str:
        want = key.casefold()
        for k, v in self.fields.items():
            if k.casefold() == want:
                return v
        return default


@dataclass
class NetNode:
    ref: str
    pin: str
    pinfunction: str = ""
    pintype: str = ""


@dataclass
class Net:
    name: str
    nodes: List[NetNode]


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def md_escape(value: object) -> str:
    """Escape Markdown table separators while preserving user text."""
    s = "" if value is None else str(value)
    return s.replace("|", r"\|")


def filename_safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", s)


def starts_ci(s: str, prefix: str) -> bool:
    return s.casefold().startswith(prefix.casefold())


def natural_key(s: str):
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", s)
    ]


def component_map(components: Iterable[Component]) -> Dict[str, Component]:
    return {c.ref.casefold(): c for c in components}


def find_component(components: Dict[str, Component], ref: str) -> Optional[Component]:
    return components.get(ref.casefold())


def first_nonempty(component: Optional[Component], *names: str) -> str:
    if not component:
        return ""
    for name in names:
        value = component.get(name)
        if value:
            return value
    return ""


# ---------------------------------------------------------------------------
# Panelization
# ---------------------------------------------------------------------------

PIECES_PER_PANEL = {
    "20x20": "25",
    "20x25": "20",
    "20x33": "15",
    "20x50": "10",
    "25x20": "20",
    "25x25": "16",
    "25x33": "12",
    "25x50": "8",
    "33x20": "15",
    "33x25": "12",
    "33x33": "9",
    "33x50": "6",
    "50x20": "10",
    "50x25": "8",
    "50x33": "6",
    "50x50": "4",
    "50x75": "2",
    "75x20": "5",
    "75x25": "4",
    "75x33": "3",
    "75x50": "2",
    "75x75": "1",
    "100x20": "5",
    "100x25": "4",
    "100x33": "3",
    "100x50": "2",
    "100x100": "1",
}


def normalize_dims_key(raw: str) -> str:
    s = raw.casefold().replace("×", "x")
    s = s.replace("mm", "")
    s = re.sub(r"\s+", "", s)
    return s


def pieces_for_dimensions(raw: str) -> str:
    return PIECES_PER_PANEL.get(normalize_dims_key(raw), "")


# ---------------------------------------------------------------------------
# Ref-des classification
# ---------------------------------------------------------------------------

PART_CLASSES = [
    ("LED", "Light emitting diode"),
    ("AR", "Amplifier / Repeater"),
    ("AT", "Attenuator"),
    ("BT", "Battery / PV"),
    ("CB", "Circuit breaker"),
    ("CP", "Connector adaptor / Junction"),
    ("CR", "Current regulator"),
    ("DC", "Directional coupler"),
    ("DL", "Delay line"),
    ("DS", "Display device"),
    ("EQ", "Equalizing network"),
    ("FL", "Filter"),
    ("HP", "Hydraulic part"),
    ("HR", "Heater"),
    ("HS", "Handset"),
    ("HT", "Earphone"),
    ("HW", "Wearable HID"),
    ("HX", "HID (other)"),
    ("LS", "Audible alarm / Speaker"),
    ("MG", "Motor"),
    ("MK", "Microphone"),
    ("MP", "Mechanical part"),
    ("MT", "Measurement transducer"),
    ("PS", "Power supply"),
    ("RT", "Thermistor"),
    ("TB", "Terminal board"),
    ("TP", "Test point"),
    ("VR", "Voltage regulator"),
    ("WT", "Wiring tie point"),
    ("A", "Gyroscope / Computational / Sensor (to power)"),
    ("B", "Blower / Fan"),
    ("C", "Capacitor"),
    ("D", "Diode"),
    ("E", "Antenna / Terminal / Cell"),
    ("F", "Fuse"),
    ("G", "Oscillator / Generator"),
    ("H", "Hardware"),
    ("J", "Connector (jack)"),
    ("K", "Relay"),
    ("L", "Inductor"),
    ("M", "Module"),
    ("P", "Connector (plug)"),
    ("Q", "Transistor"),
    ("R", "Resistor"),
    ("S", "Switch"),
    ("T", "Transformer"),
    ("U", "Integrated circuit"),
    ("W", "Cable / Wire"),
    ("X", "Holder / Socket"),
    ("Y", "Crystal / Resonator"),
]


def classify_part(refdes: str) -> str:
    r = refdes.upper()
    for prefix, label in PART_CLASSES:
        if r.startswith(prefix):
            return label
    return "OTHER"


def excluded_from_partlist(refdes: str) -> bool:
    prefixes = ("P+", "P-", "GND", "SHEET", "U$", "PCB", "DWG", "NC")
    return any(starts_ci(refdes, p) for p in prefixes)


def excluded_from_netlist(refdes: str) -> bool:
    prefixes = ("GND", "P+", "P-", "VCC", "VDD", "VSS", "VEE", "DWG")
    return any(starts_ci(refdes, p) for p in prefixes)


# ---------------------------------------------------------------------------
# KiCad CLI / XML parsing
# ---------------------------------------------------------------------------

def find_kicad_cli(explicit: Optional[str]) -> str:
    if explicit:
        return explicit

    found = shutil.which("kicad-cli")
    if found:
        return found

    # Common Windows locations. Add another entry here if your install differs.
    candidates = [
        Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"),
        Path(r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"),
        Path(r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError(
        "Could not find kicad-cli. Put it on PATH or pass --kicad-cli "
        r'"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe".'
    )


def export_kicad_xml(kicad_cli: str, schematic: Path, xml_path: Path) -> None:
    cmd = [
        kicad_cli,
        "sch",
        "export",
        "netlist",
        "--format",
        "kicadxml",
        "--output",
        str(xml_path),
        str(schematic),
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            "KiCad netlist export failed.\n\n"
            f"Command:\n{' '.join(cmd)}\n\n"
            f"stdout:\n{result.stdout}\n\n"
            f"stderr:\n{result.stderr}"
        )


def child_text(parent: ET.Element, tag: str) -> str:
    node = parent.find(tag)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def parse_xml_netlist(xml_path: Path) -> Tuple[List[Component], List[Net]]:
    root = ET.parse(xml_path).getroot()

    components: List[Component] = []
    comps = root.find("components")
    if comps is not None:
        for node in comps.findall("comp"):
            ref = node.attrib.get("ref", "").strip()
            fields: Dict[str, str] = {}

            fields_node = node.find("fields")
            if fields_node is not None:
                for field_node in fields_node.findall("field"):
                    name = field_node.attrib.get("name", "").strip()
                    value = (field_node.text or "").strip()
                    if name:
                        fields[name] = value

            # Newer exporters may expose some properties separately.
            properties_node = node.find("properties")
            if properties_node is not None:
                for prop_node in properties_node.findall("property"):
                    name = prop_node.attrib.get("name", "").strip()
                    value = prop_node.attrib.get("value", "").strip()
                    if name and name not in fields:
                        fields[name] = value

            libsource = node.find("libsource")
            lib = ""
            part = ""
            if libsource is not None:
                lib = libsource.attrib.get("lib", "")
                part = libsource.attrib.get("part", "")

            components.append(
                Component(
                    ref=ref,
                    value=child_text(node, "value"),
                    footprint=child_text(node, "footprint"),
                    lib=lib,
                    part=part,
                    fields=fields,
                )
            )

    nets: List[Net] = []
    nets_node = root.find("nets")
    if nets_node is not None:
        for net_node in nets_node.findall("net"):
            name = net_node.attrib.get("name", "").strip() or "(unnamed)"
            nodes: List[NetNode] = []

            for node in net_node.findall("node"):
                nodes.append(
                    NetNode(
                        ref=node.attrib.get("ref", "").strip(),
                        pin=node.attrib.get("pin", "").strip(),
                        pinfunction=node.attrib.get("pinfunction", "").strip(),
                        pintype=node.attrib.get("pintype", "").strip(),
                    )
                )
            nets.append(Net(name=name, nodes=nodes))

    return components, nets


# ---------------------------------------------------------------------------
# Minimal S-expression reader, used only to locate graphical NOTES text.
# ---------------------------------------------------------------------------

def sexpr_tokens(text: str):
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        if ch.isspace():
            i += 1
            continue

        if ch == "(":
            yield "("
            i += 1
            continue

        if ch == ")":
            yield ")"
            i += 1
            continue

        if ch == '"':
            i += 1
            out = []
            while i < n:
                ch = text[i]
                if ch == '"':
                    i += 1
                    break
                if ch == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    escapes = {
                        "n": "\n",
                        "r": "\r",
                        "t": "\t",
                        '"': '"',
                        "\\": "\\",
                    }
                    if nxt in escapes:
                        out.append(escapes[nxt])
                        i += 2
                        continue
                out.append(ch)
                i += 1
            yield "".join(out)
            continue

        start = i
        while i < n and not text[i].isspace() and text[i] not in "()":
            i += 1
        yield text[start:i]


def parse_sexpr(text: str):
    stack: List[list] = []
    root = None

    for token in sexpr_tokens(text):
        if token == "(":
            item: list = []
            if stack:
                stack[-1].append(item)
            stack.append(item)
            if root is None:
                root = item
        elif token == ")":
            if not stack:
                raise ValueError("Unexpected ')' in schematic")
            stack.pop()
        else:
            if not stack:
                continue
            stack[-1].append(token)

    if stack:
        raise ValueError("Unclosed '(' in schematic")
    return root


def walk_lists(node):
    if isinstance(node, list):
        yield node
        for child in node:
            yield from walk_lists(child)


def extract_notes(schematic: Path) -> str:
    """
    Find the first graphical text object whose text starts with NOTES:.

    Unlike the EAGLE version, this does not depend on an exact XY coordinate.
    That is intentional: KiCad UUIDs/coordinates should not be necessary to
    identify the notes block.
    """
    raw = schematic.read_text(encoding="utf-8", errors="replace")
    tree = parse_sexpr(raw)

    for item in walk_lists(tree):
        if len(item) >= 2 and item[0] == "text" and isinstance(item[1], str):
            value = item[1]
            if value.lstrip().upper().startswith("NOTES:"):
                stripped = value.lstrip()
                return stripped[len("NOTES:"):].lstrip()

    return ""


# ---------------------------------------------------------------------------
# Markdown writers
# ---------------------------------------------------------------------------

def write_header(out: List[str]) -> None:
    out += [
        "# miniPCB",
        "",
        "**Circuit boards for electronics education.**",
        "",
        "[www.minipcb.com](https://www.minipcb.com)  ",
        "[youtube.com/@minipcb](https://www.youtube.com/@minipcb)  ",
        "[github.com/miniPCB/minipcb.github.io](https://github.com/miniPCB/minipcb.github.io)",
        "",
        "---",
        "",
        "# Schematic Export (Markdown)",
        "",
        f"**Python Exporter Revision Date:** {SCRIPT_REVISION_DATE}  ",
        "",
    ]


def write_circuit_identification(
    out: List[str], comps: Dict[str, Component]
) -> Tuple[str, str]:
    pcb = find_component(comps, PCB_PART)
    dwg = find_component(comps, DWG_PART)

    pn = pcb.get("PART_NUMBER") if pcb else ""
    rev = pcb.get("REVISION") if pcb else ""
    title = pcb.get("TITLE") if pcb else ""
    dims = dwg.get("DIMENSIONS") if dwg else ""
    pieces = pieces_for_dimensions(dims)

    out += [
        "# Circuit Identification",
        "",
        "| Field            | Value |",
        "| ---------------- | ----- |",
        f"| Part Number      | {md_escape(pn)} |",
        f"| Revision         | {md_escape(rev)} |",
        f"| Title            | {md_escape(title)} |",
        f"| PCB Dimensions   | {md_escape(dims)} |",
        f"| Pieces per Panel | {md_escape(pieces)} |",
        "",
    ]
    return pn, rev


def write_revision_history(out: List[str], comps: Dict[str, Component]) -> None:
    sheet = find_component(comps, SHEET_PART)
    if not sheet:
        return

    rows = [
        (
            first_nonempty(sheet, "REV_1", "REVA"),
            first_nonempty(sheet, "DATE_1", "DATEA"),
            first_nonempty(sheet, "DESCRIPTION_1", "DESCRIPTIONA"),
            sheet.get("REVA_INSTRUCTABLES"),
        ),
        (
            first_nonempty(sheet, "REV_2", "REVB"),
            first_nonempty(sheet, "DATE_2", "DATEB"),
            first_nonempty(sheet, "DESCRIPTION_2", "DESCRIPTIONB"),
            sheet.get("REVB_INSTRUCTABLES"),
        ),
        (
            first_nonempty(sheet, "REV_3", "REVC"),
            first_nonempty(sheet, "DATE_3", "DATEC"),
            first_nonempty(sheet, "DESCRIPTION_3", "DESCRIPTIONC"),
            sheet.get("REVC_INSTRUCTABLES"),
        ),
    ]
    rows = [r for r in rows if r[0]]
    if not rows:
        return

    out += [
        "# Revision History",
        "",
        "| Revision | Date | Description | Instructables |",
        "|----------|------|-------------|---------------|",
    ]

    for rev, date, desc, url in rows:
        link = f"[{url}]({url})" if url else ""
        out.append(
            f"| {md_escape(rev)} | {md_escape(date)} | "
            f"{md_escape(desc)} | {link} |"
        )
    out.append("")


def append_resource(out: List[str], label: str, url: str) -> None:
    if url:
        out.append(f"| {label} | [{url}]({url}) |")


def write_published_resources(
    out: List[str],
    comps: Dict[str, Component],
    pn: str,
    rev: str,
    sheet_count: int = 1,
) -> None:
    dwg = find_component(comps, DWG_PART)
    stem = filename_safe(f"{pn}_{rev}") if pn and rev else ""

    out += [
        "# Published Resources",
        "",
        "| Resource | URL |",
        "|----------|-----|",
    ]

    if dwg:
        fields = [
            ("Part Webpage", "PART_WEBPAGE"),
            ("Datasheet", "DATASHEET"),
            ("Engineering Notes", "ENG_NOTES"),
            ("Test Script", "TEST_SCRIPT"),
            ("Gerbers", "GERBERS"),
            ("LTspice", "LTSPICE"),
            ("CAD Source", "CAD_SOURCE"),
            ("Design Review Video", "VID_DESIGN_REVIEW"),
            ("Build Video", "VID_BUILD"),
            ("Test Video", "VID_TEST"),
            ("Demo Video", "VID_DEMO"),
            ("Tutorial Video", "VID_TUTORIAL"),
        ]
        for label, key in fields:
            append_resource(out, label, dwg.get(key))

    if stem:
        append_resource(out, "Schematic JSON", GITHUB_BASE + f"json/{stem}_sch.json")
        append_resource(out, "Schematic Markdown", GITHUB_BASE + f"md/{stem}_sch.md")

    if pn:
        append_resource(out, "Board Top View", GITHUB_BASE + f"images/{pn}_components_top.png")
        append_resource(out, "Board Bottom View", GITHUB_BASE + f"images/{pn}_components_bottom.png")
        for index in range(1, sheet_count + 1):
            append_resource(
                out,
                f"Schematic Image, Sheet {index}",
                GITHUB_BASE + f"images/{pn}_schematic_{index:02d}.png",
            )

    out.append("")


def write_schematic_notes(out: List[str], notes: str) -> None:
    if not notes:
        return
    out += ["# Schematic Notes", "", notes.rstrip(), ""]


def connector_label(component: Optional[Component], pin: str) -> str:
    if not component:
        return ""
    return component.get(f"pin{pin}")


def write_netlist(
    out: List[str],
    nets: List[Net],
    comps: Dict[str, Component],
) -> None:
    p1 = find_component(comps, TARGET_CONN)

    out += [
        "# Netlist",
        "",
        "| Net | Part | Pad | Pin | Sheet |",
        "|-----|------|-----|-----|-------|",
    ]

    for net in sorted(nets, key=lambda n: natural_key(n.name)):
        for node in sorted(net.nodes, key=lambda n: (natural_key(n.ref), natural_key(n.pin))):
            if excluded_from_netlist(node.ref):
                continue

            pin_name = node.pinfunction or node.pin

            if node.ref.casefold() == TARGET_CONN.casefold():
                pin_name = connector_label(p1, node.pin) or node.pin

            # kicadxml already resolves the actual project sheet internally.
            # The legacy table expects a sheet field, so root is "1" here.
            # See --verbose/next revision if explicit hierarchical sheet
            # numbering is desired.
            sheet = "1"

            out.append(
                f"| {md_escape(net.name)} | {md_escape(node.ref)} | "
                f"{md_escape(node.pin)} | {md_escape(pin_name)} | {sheet} |"
            )

    out.append("")


def write_partlist(out: List[str], components: List[Component]) -> None:
    out += [
        "# Partlist",
        "",
        "| REF DES | PART TYPE | VALUE / DESCRIPTION | FUNCTION |",
        "|---------|-----------|---------------------|----------|",
    ]

    for c in sorted(components, key=lambda c: natural_key(c.ref)):
        if not c.ref or excluded_from_partlist(c.ref):
            continue
        out.append(
            f"| {md_escape(c.ref)} | {md_escape(classify_part(c.ref))} | "
            f"{md_escape(c.value)} | {md_escape(c.get('FUNCTION'))} |"
        )

    out.append("")


def write_test_points(out: List[str], components: List[Component]) -> None:
    tps = [c for c in components if starts_ci(c.ref, "TP")]
    if not tps:
        return

    out += [
        "# Test Points",
        "",
        "| Test Point | Function |",
        "|------------|----------|",
    ]
    for c in sorted(tps, key=lambda c: natural_key(c.ref)):
        out.append(f"| {md_escape(c.ref)} | {md_escape(c.get('FUNCTION'))} |")
    out.append("")


def numeric_field_suffix(field_name: str, prefix: str) -> Optional[int]:
    m = re.fullmatch(re.escape(prefix) + r"(\d+)", field_name, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def write_pinout(out: List[str], comps: Dict[str, Component]) -> None:
    conn = find_component(comps, TARGET_CONN)
    if not conn:
        out += [f"_No connector {TARGET_CONN} found in schematic._", ""]
        return

    pins: List[Tuple[int, str, str]] = []
    for key, value in conn.fields.items():
        idx = numeric_field_suffix(key, "pin")
        if idx is None:
            continue
        note = conn.get(f"NOTE{idx}")
        pins.append((idx, value, note))

    if not pins:
        return

    out += [
        f"# Pinout Description Table, {TARGET_CONN}  ",
        "",
        "| Pin | Label | Notes |",
        "|-----|-------|-------|",
    ]
    for idx, label, note in sorted(pins):
        out.append(
            f"| {idx} | {md_escape(label)} | {md_escape(note)} |"
        )
    out.append("")


# ---------------------------------------------------------------------------
# Schematic sheet counting
# ---------------------------------------------------------------------------

def count_schematic_sheets(schematic: Path) -> int:
    """
    Count root + hierarchical sheet symbols in the root .kicad_sch.

    This is a practical approximation for generating deterministic miniPCB
    image links. For repeated hierarchical sheet instances, the count may not
    exactly match KiCad's plotted page count.
    """
    raw = schematic.read_text(encoding="utf-8", errors="replace")
    try:
        tree = parse_sexpr(raw)
    except Exception:
        return 1

    count = 1
    if isinstance(tree, list):
        for item in tree:
            if isinstance(item, list) and item and item[0] == "sheet":
                count += 1
    return max(1, count)


# ---------------------------------------------------------------------------
# Main document generation
# ---------------------------------------------------------------------------

def generate_markdown(
    schematic: Path,
    components: List[Component],
    nets: List[Net],
) -> Tuple[str, str]:
    comps = component_map(components)
    notes = extract_notes(schematic)
    sheet_count = count_schematic_sheets(schematic)

    out: List[str] = []
    write_header(out)
    pn, rev = write_circuit_identification(out, comps)
    write_revision_history(out, comps)
    write_published_resources(out, comps, pn, rev, sheet_count)
    write_schematic_notes(out, notes)
    write_netlist(out, nets, comps)
    write_partlist(out, components)
    write_test_points(out, components)
    write_pinout(out, comps)

    if pn and rev:
        stem = filename_safe(f"{pn}_{rev}")
    elif pn:
        stem = filename_safe(f"{pn}_REV")
    elif rev:
        stem = filename_safe(f"{schematic.stem}_{rev}")
    else:
        stem = filename_safe(schematic.stem)

    return "\n".join(out).rstrip() + "\n", f"{stem}_sch.md"


def resolve_output_path(value: Optional[Path], suggested_name: str) -> Path:
    if value is None:
        return Path.cwd() / suggested_name

    # Existing directory, or a path without .md, is treated as a directory.
    if value.exists() and value.is_dir():
        return value / suggested_name
    if value.suffix.casefold() != ".md":
        return value / suggested_name
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a miniPCB-style Markdown document from a KiCad schematic."
    )
    parser.add_argument("schematic", type=Path, help="Input .kicad_sch file")
    parser.add_argument(
        "-o", "--output", type=Path,
        help="Output .md file or output directory. Default: current directory."
    )
    parser.add_argument(
        "--mirror", type=Path,
        help="Optional second output .md file or directory."
    )
    parser.add_argument(
        "--kicad-cli",
        help="Explicit path to kicad-cli executable."
    )
    parser.add_argument(
        "--keep-xml",
        type=Path,
        help="Optionally save the intermediate KiCad XML netlist here."
    )
    args = parser.parse_args()

    schematic = args.schematic.resolve()
    if not schematic.exists():
        parser.error(f"Schematic not found: {schematic}")
    if schematic.suffix.casefold() != ".kicad_sch":
        parser.error("Input must be a .kicad_sch file")

    try:
        kicad_cli = find_kicad_cli(args.kicad_cli)

        with tempfile.TemporaryDirectory(prefix="minipcb_kicad_") as temp_dir:
            xml_path = Path(temp_dir) / "netlist.xml"
            export_kicad_xml(kicad_cli, schematic, xml_path)

            if args.keep_xml:
                args.keep_xml.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(xml_path, args.keep_xml)

            components, nets = parse_xml_netlist(xml_path)

        markdown, suggested_name = generate_markdown(
            schematic,
            components,
            nets,
        )

        out_path = resolve_output_path(args.output, suggested_name)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")

        written = [out_path]

        if args.mirror:
            mirror_path = resolve_output_path(args.mirror, suggested_name)
            mirror_path.parent.mkdir(parents=True, exist_ok=True)
            mirror_path.write_text(markdown, encoding="utf-8")
            written.append(mirror_path)

        print("Schematic export complete:")
        for path in written:
            print(f"  {path}")

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
