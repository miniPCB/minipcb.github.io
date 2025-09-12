# 04A-00 A1-01 — Analysis Plans & Reports Prompt
You are an expert electronics engineer and reliability analyst. Using the provided circuit context, generate the following **deliverables** for Part Number **04A-00**, Revision **A1-01**:
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
| Part Number      | 04A-00 |
| Revision         | A1-01 |
| Title            | VOLTAGE FOLLOWER |
| PCB Dimensions   | 33 mm x 25 mm |
| Pieces per Panel | 12 |

# Netlist (Schematic)

| Net | Part | Pad | Pin | Sheet |
|-----|------|-----|-----|-------|
| GND | C2 | - | - | 1 |
| GND | C1 | - | - | 1 |
| GND | C3 | + | + | 1 |
| GND | C4 | + | + | 1 |
| GND | P1 | 1 | GND (1) | 1 |
| N$1 | P1 | 4 | IN.A (4) | 1 |
| N$1 | U1 | +IN | +IN | 1 |
| N$2 | U1 | -IN | -IN | 1 |
| N$2 | U1 | OUT | OUT | 1 |
| N$2 | P1 | 6 | OUT.A (6) | 1 |
| N$3 | P1 | 5 | IN.B (5) | 1 |
| N$3 | U1 | +IN | +IN | 1 |
| N$4 | U1 | -IN | -IN | 1 |
| N$4 | U1 | OUT | OUT | 1 |
| N$4 | P1 | 7 | OUT.B (7) | 1 |
| V+ | P1 | 2 | V+ (2) | 1 |
| V+ | C2 | + | + | 1 |
| V+ | C1 | + | + | 1 |
| V+ | U1 | V+ | V+ | 1 |
| V- | P1 | 3 | V- (3) | 1 |
| V- | U1 | V- | V- | 1 |
| V- | C3 | - | - | 1 |
| V- | C4 | - | - | 1 |

# Partlist (Schematic)

| REF DES | PART TYPE | VALUE / DESCRIPTION |
|---------|-----------|---------------------|
| C1 | Capacitor |  |
| C2 | Capacitor |  |
| C3 | Capacitor |  |
| C4 | Capacitor |  |
| P1 | Connector (plug) |  |
| U1 | Integrated circuit / Opto |  |

# Pinout Description Table, P1  

| Pin | Label | Notes |
|-----|-------|-------|
| 1 | GND |  |
| 2 | V+ |  |
| 3 | V- |  |
| 4 | IN.A |  |
| 5 | IN.B |  |
| 6 | OUT.A |  |
| 7 | OUT.B |  |
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

**Decoupling (C1–C4):**

- Typical: per rail, **0.1 µF X7R** at each op-amp supply pin + **4.7–10 µF** bulk nearby.
    
- Range: 10 nF–1 µF (ceramic) + 1–47 µF (bulk).
    
- Trade-offs: bigger bulk improves transient load rejection but increases inrush; 0.1 µF keeps HF impedance low.
    

**Input/output nodes (no R/C shown):**

- Add optional **Rout 22–100 Ω** for cable drive/isolation; optional **Cin (AC-coupling) 1–10 µF** with **Rin to GND 100 kΩ** to set a sub-Hz corner if needed.
    
- Trade-offs: Rout improves stability with capacitive loads but adds output drop; AC coupling sets low-frequency roll-off (fc).
    

**Op-amp U1:**

- Choose a unity-gain-stable device with GBP ≥ max signal bandwidth × 10. For audio/DC work: **GBP 5–20 MHz**, **SR ≥ 2×(2π fmax Vpk)**, **rail-to-rail in/out** if single-supply.
    
- Trade-offs: lower noise op-amps often need more current; CMOS inputs minimize Ib-_R_ error on high-impedance sources.
    

**Connector P1:** pinout exposes dual channels in/out and supplies for easy bring-up (GND, V±, IN.A/B, OUT.A/B).
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

# `04A-00_A1-01_epsa_plan.md`
(...content...)

- Include **FULL tables** (no truncation). If a table is extremely large, split across multiple tables or provide an attached CSV/JSON in addition to the Markdown.
- Include a **TODO** list per deliverable for any data you need from CAD (e.g., exact stackup, trace widths, thermal limits).
## Safety & Practical Notes
- If the circuit interacts with power electronics or high voltages/currents, include a **Safety Considerations** subsection.
- If any datasheet-dependent parameter is required (e.g., SOA, temp coefficients), mention the parameter and where it would be sourced.
