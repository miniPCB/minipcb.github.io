# 04A-04 A1-02 — Analysis Plans & Reports Prompt
You are an expert electronics engineer and reliability analyst. Using the provided circuit context, generate the following **deliverables** for Part Number **04A-04**, Revision **A1-02**:
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
| Part Number      | 04A-04 |
| Revision         | A1-02 |
| Title            | NON-INVERTING SUMMING AMPLIFIER |
| PCB Dimensions   | 75 mm x 50 mm |
| Pieces per Panel | 2 |

# Netlist (Schematic)

| Net | Part | Pad | Pin | Sheet |
|-----|------|-----|-----|-------|
| BIAS | C3 | + | + | 1 |
| BIAS | R2 | S | S | 1 |
| BIAS | C5 | + | + | 1 |
| BIAS | U1 | +IN | +IN | 1 |
| BIAS | TP4 | 1 | 1 | 1 |
| BIAS | R4 | 1 | 1 | 1 |
| BIAS_CONTROL | TP1 | 1 | 1 | 1 |
| BIAS_CONTROL | R4 | 2 | 2 | 1 |
| BIAS_CONTROL | P1 | 6 | 6 | 1 |
| GND | P1 | 1 | 1 | 1 |
| GND | C2 | - | - | 1 |
| GND | C4 | - | - | 1 |
| GND | C3 | - | - | 1 |
| GND | C5 | - | - | 1 |
| GND | TP10 | 1 | 1 | 1 |
| GND | R12 | 2 | 2 | 1 |
| GND | P1 | 7 | 7 | 1 |
| GND | R6 | 2 | 2 | 1 |
| GND | C6 | + | + | 1 |
| GND | C7 | + | + | 1 |
| GND | R8 | 2 | 2 | 1 |
| IN | R5 | 2 | 2 | 1 |
| IN | TP5 | 1 | 1 | 1 |
| IN | P1 | 4 | 4 | 1 |
| N$1 | R11 | S | S | 1 |
| N$1 | R10 | 2 | 2 | 1 |
| N$2 | P1 | 5 | 5 | 1 |
| N$2 | R13 | 1 | 1 | 1 |
| OUT | TP12 | 1 | 1 | 1 |
| OUT | U1 | OUT | OUT | 1 |
| OUT | R9 | 2 | 2 | 1 |
| OUT | C8 | + | + | 1 |
| OUT | R12 | 1 | 1 | 1 |
| OUT | R11 | A | A | 1 |
| OUT | R13 | 2 | 2 | 1 |
| POT.1 | R2 | A | A | 1 |
| POT.1 | R3 | 2 | 2 | 1 |
| POT.1 | TP3 | 1 | 1 | 1 |
| POT.1 | C1 | - | - | 1 |
| POT.3 | R2 | E | E | 1 |
| POT.3 | R1 | 1 | 1 | 1 |
| POT.3 | TP2 | 1 | 1 | 1 |
| POT.3 | C1 | + | + | 1 |
| V+ | P1 | 2 | 2 | 1 |
| V+ | C2 | + | + | 1 |
| V+ | C4 | + | + | 1 |
| V+ | R1 | 2 | 2 | 1 |
| V+ | U1 | V+ | V+ | 1 |
| V+ | TP9 | 1 | 1 | 1 |
| V- | P1 | 3 | 3 | 1 |
| V- | C6 | - | - | 1 |
| V- | C7 | - | - | 1 |
| V- | U1 | V- | V- | 1 |
| V- | TP11 | 1 | 1 | 1 |
| V- | R3 | 1 | 1 | 1 |
| VFB | R9 | 1 | 1 | 1 |
| VFB | C8 | - | - | 1 |
| VFB | R8 | 1 | 1 | 1 |
| VFB | U1 | -IN | -IN | 1 |
| VFB | TP8 | 1 | 1 | 1 |
| VFB | R10 | 1 | 1 | 1 |
| VREF | U1 | -IN | -IN | 1 |
| VREF | U1 | OUT | OUT | 1 |
| VREF | R7 | 2 | 2 | 1 |
| VREF | TP6 | 1 | 1 | 1 |
| VREF_FILTERED | R7 | 1 | 1 | 1 |
| VREF_FILTERED | R5 | 1 | 1 | 1 |
| VREF_FILTERED | TP7 | 1 | 1 | 1 |
| VREF_FILTERED | U1 | +IN | +IN | 1 |
| VREF_FILTERED | R6 | 1 | 1 | 1 |

# Partlist (Schematic)

| REF DES | PART TYPE | VALUE / DESCRIPTION |
|---------|-----------|---------------------|
| C1 | Capacitor |  |
| C2 | Capacitor |  |
| C3 | Capacitor |  |
| C4 | Capacitor |  |
| C5 | Capacitor |  |
| C6 | Capacitor |  |
| C7 | Capacitor |  |
| C8 | Capacitor |  |
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
| R10 | Resistor |  |
| R11 | Resistor |  |
| R12 | Resistor |  |
| R13 | Resistor |  |
| TP1 | Test point |  |
| TP2 | Test point |  |
| TP3 | Test point |  |
| TP4 | Test point |  |
| TP5 | Test point |  |
| TP6 | Test point |  |
| TP7 | Test point |  |
| TP8 | Test point |  |
| TP9 | Test point |  |
| TP10 | Test point |  |
| TP11 | Test point |  |
| TP12 | Test point |  |
| U1 | Integrated circuit / Opto |  |

# Pinout Description Table, P1  

| Pin | Label | Notes |
|-----|-------|-------|
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

**Summing/gain (R5 into +IN; R9/R8 set Av; R10 series in loop; C8 comp):**

- **Av ≈ 1 + R9/R8**. Start **R8 4.7–10 kΩ**, **R9 10–100 kΩ**.
    
- **R5** sets input scaling; choose **1–20 kΩ** so the source isn’t heavily loaded.
    
- **C8 10–47 pF** across VFB helps stability with multiple summed sources.
    
- Trade-offs: large R values reduce input loading but increase noise and bias errors.
    

**Bias/reference (R1–R4, R6–R7; C1, C3, C5):**

- Pot **R2 10–100 kΩ**; filters **0.47–4.7 µF** on BIAS/VREF nodes.
    

**Supplies/decoupling (C2, C4, C6, C7):** as usual.
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

# `04A-04_A1-02_epsa_plan.md`
(...content...)

- Include **FULL tables** (no truncation). If a table is extremely large, split across multiple tables or provide an attached CSV/JSON in addition to the Markdown.
- Include a **TODO** list per deliverable for any data you need from CAD (e.g., exact stackup, trace widths, thermal limits).
## Safety & Practical Notes
- If the circuit interacts with power electronics or high voltages/currents, include a **Safety Considerations** subsection.
- If any datasheet-dependent parameter is required (e.g., SOA, temp coefficients), mention the parameter and where it would be sourced.
