# 04A-04 A1-02 — Feedback

The datasheet for PN: 04A-04, REV: A1-02, presents a comprehensive overview of the non-inverting summing amplifier. However, there are several issues related to component identifiers, net names, and documentation consistency that need to be addressed to ensure clarity and accuracy.

| #  | Severity | Category       | Location                | Finding                                                                 | Suggested Fix                                                      | Confidence |
|----|----------|----------------|-------------------------|------------------------------------------------------------------------|-------------------------------------------------------------------|------------|
| 1  | High     | Refdes         | Netlist                 | Refdes `R11` uses pin `A`, which is not standard.                       | Verify and correct the pin designation for `R11`.                  | High       |
| 2  | High     | Net Name       | Netlist                 | Net `BIAS` is not in the allowed list.                                 | Change `BIAS` to an allowed net name.                              | High       |
| 3  | High     | Net Name       | Netlist                 | Net `BIAS_CONTROL` is not in the allowed list.                         | Change `BIAS_CONTROL` to an allowed net name.                      | High       |
| 4  | High     | Net Name       | Netlist                 | Net `IN` is not in the allowed list.                                   | Change `IN` to an allowed net name.                                | High       |
| 5  | High     | Net Name       | Netlist                 | Net `OUT` is not in the allowed list.                                  | Change `OUT` to an allowed net name.                               | High       |
| 6  | High     | Net Name       | Netlist                 | Net `POT.1` is not in the allowed list.                                | Change `POT.1` to an allowed net name.                             | High       |
| 7  | High     | Net Name       | Netlist                 | Net `POT.3` is not in the allowed list.                                | Change `POT.3` to an allowed net name.                             | High       |
| 8  | High     | Net Name       | Netlist                 | Net `VFB` is not in the allowed list.                                  | Change `VFB` to an allowed net name.                               | High       |
| 9  | High     | Net Name       | Netlist                 | Net `VREF` is not in the allowed list.                                 | Change `VREF` to an allowed net name.                              | High       |
| 10 | High     | Net Name       | Netlist                 | Net `VREF_FILTERED` is not in the allowed list.                        | Change `VREF_FILTERED` to an allowed net name.                     | High       |
| 11 | Medium   | Documentation  | Partlist                | Missing values/descriptions for all components.                        | Add values/descriptions for each component in the partlist.        | Medium     |
| 12 | Medium   | Documentation  | Pinout Description Table| Table is empty and lacks pin descriptions for P1.                      | Populate the table with pin descriptions for P1.                   | Medium     |
| 13 | Low      | Typo           | Manual Commentary       | "comp" should be "compensation" for clarity.                           | Change "comp" to "compensation".                                   | High       |
| 14 | Low      | Style          | Manual Commentary       | Inconsistent use of units (e.g., "kΩ" vs "kOhm").                      | Standardize unit representation throughout the document.           | High       |

### Checks Performed

- Verified refdes against the allowed list.
- Checked net names against the allowed list.
- Reviewed for typos and unit/style consistency.
- Ensured completeness of component descriptions and pinout tables.