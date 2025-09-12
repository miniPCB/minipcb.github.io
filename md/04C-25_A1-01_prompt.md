# 04C-25 A1-01 — Analysis Plans & Reports Prompt
You are an expert electronics engineer and reliability analyst. Using the provided circuit context, generate the following **deliverables** for Part Number **04C-25**, Revision **A1-01**:
## Deliverables
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

## Full Source Context (Verbatim)
The following sections include the **complete** schematic export and manual commentary to ensure fidelity and traceability.

<details>
<summary>Full Schematic Markdown (verbatim)</summary>

```markdown
# Schematic Export (Markdown)

**ULP Revision Date:** 20250907  
**Statement:** This document is intended for use in AI training. 

# Circuit Identification

| Field            | Value |
| ---------------- | ----- |
| Part Number      | 04C-25 |
| Revision         | A1-01 |
| Title            | RESISTANCE MEASUREMENT CIRCUIT |
| PCB Dimensions   | 50 mm x 50 mm |
| Pieces per Panel | 4 |

# Netlist (Schematic)

| Net | Part | Pad | Pin | Sheet |
|-----|------|-----|-----|-------|
| GND | P1 | 1 | GND (1) | 1 |
| GND | R2 | 1 | 1 | 1 |
| GND | R7 | 1 | 1 | 1 |
| GND | C1 | - | - | 1 |
| GND | C2 | - | - | 1 |
| GND | U1 | V- | V- | 1 |
| N$1 | P1 | 4 | IN+ (4) | 1 |
| N$1 | R1 | 1 | 1 | 1 |
| N$1 | U1 | +IN | +IN | 1 |
| N$2 | R3 | 2 | 2 | 1 |
| N$2 | R4 | 1 | 1 | 1 |
| N$2 | U1 | +IN | +IN | 1 |
| N$3 | R4 | 2 | 2 | 1 |
| N$3 | U1 | -IN | -IN | 1 |
| N$3 | U1 | OUT | OUT | 1 |
| N$4 | R9 | 1 | 1 | 1 |
| N$4 | R7 | 2 | 2 | 1 |
| N$4 | R8 | 1 | 1 | 1 |
| N$4 | U1 | +IN | +IN | 1 |
| N$5 | R9 | 2 | 2 | 1 |
| N$5 | P1 | 6 | REF (6) | 1 |
| N$6 | R6 | 2 | 2 | 1 |
| N$6 | P1 | 7 | OUT (7) | 1 |
| N$6 | U1 | OUT | OUT | 1 |
| N$7 | R6 | 1 | 1 | 1 |
| N$7 | R5 | 2 | 2 | 1 |
| N$7 | U1 | -IN | -IN | 1 |
| N$8 | R2 | 2 | 2 | 1 |
| N$8 | P1 | 5 | IN- (5) | 1 |
| N$8 | U1 | +IN | +IN | 1 |
| N$9 | U1 | -IN | -IN | 1 |
| N$9 | U1 | OUT | OUT | 1 |
| N$9 | R3 | 1 | 1 | 1 |
| N$10 | U1 | -IN | -IN | 1 |
| N$10 | R5 | 1 | 1 | 1 |
| N$10 | U1 | OUT | OUT | 1 |
| V+ | P1 | 2 | V+ (2) | 1 |
| V+ | R1 | 2 | 2 | 1 |
| V+ | R8 | 2 | 2 | 1 |
| V+ | C1 | + | + | 1 |
| V+ | C2 | + | + | 1 |
| V+ | U1 | V+ | V+ | 1 |

# Partlist (Schematic)

| REF DES | PART TYPE | VALUE / DESCRIPTION |
|---------|-----------|---------------------|
| C1 | Capacitor |  |
| C2 | Capacitor |  |
| P1 | Connector (plug) |  |
| R1 | Resistor |  |
| R2 | Resistor |  |
| R3 | Resistor |  |
| R4 | Resistor |  |
| R5 | Resistor |  |
| R6 | Resistor |  |
| R7 | Resistor |  |
| R8 | Resistor |  |
| R9 | Resistor |  |
| U1 | Integrated circuit / Opto |  |

# Pinout Description Table, P1  

| Pin | Label | Notes |
|-----|-------|-------|
| 1 | GND |  |
| 2 | V+ |  |
| 3 | NC |  |
| 4 | IN+ |  |
| 5 | IN- |  |
| 6 | REF |  |
| 7 | OUT |  |
```
</details>


<details>
<summary>Manual Commentary (verbatim)</summary>

```markdown
# Manual Commentary (Markdown)

## Revision History

| Revision | Date       | Change Summary  |
| -------- | ---------- | --------------- |
| -        | 2025-09-09 | Initial release |

## Circuit Description

**Excitation/scale (R1 to V+, R2 to GND, R3–R6 around IN± and –IN):**

- Typical approach: force a known current through Rx or sense a divider.
    
- **R1, R8, R9 (REF path)** in the **10–100 kΩ** range to create a stable reference (exported on P1.6).
    
- **R3–R6** set transimpedance or gain: start **4.99–49.9 kΩ** precision.
    
- Trade-offs: higher R improves input loading but increases noise; precision (0.1% or better) improves measurement linearity.
    

**Output/load (R6 to OUT, R7–R9 REF network):**

- Keep **R6 1–10 kΩ** so the op-amp has a reasonable feedback impedance.
    
- Filter REF with **1–10 µF** if you need low noise; bleed with **100 kΩ** to fix DC points.
    

**Supplies (C1/C2):** 0.1 µF + 4.7–10 µF.

**Op-amp:** low Vos/Ib are important for precision; if measuring to GΩ levels, consider a JFET/CMS op-amp and guard rings on PCB.
```
</details>

## TestBASE Test Item Template (for any required experimental verification)
Use/extend the following JSON object for individual test items (Plan → Report mapping). Provide at least one example filled-out test for each critical function or risk area you identify.

```json
{
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
}
```
## Output Requirements
- Produce **each deliverable** as a separate Markdown section in your response, prefixed with a level-1 heading containing the target filename in backticks. Example:

# `04C-25_A1-01_epsa_plan.md`
(...content...)

- Include **FULL tables** (no truncation). If a table is extremely large, split across multiple tables or provide an attached CSV/JSON in addition to the Markdown.
- Include a **TODO** list per deliverable for any data you need from CAD (e.g., exact stackup, trace widths, thermal limits).
## Safety & Practical Notes
- If the circuit interacts with power electronics or high voltages/currents, include a **Safety Considerations** subsection.
- If any datasheet-dependent parameter is required (e.g., SOA, temp coefficients), mention the parameter and where it would be sourced.
