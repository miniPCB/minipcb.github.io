# Voltage Divider — Schematic Export (Markdown)

miniPCB · Circuit boards for electronics education

This hand-authored reference describes the calculator's ideal DC circuit; it is
not an EAGLE board export. The downloadable LTspice file contains the default
values below. Calculator edits do not modify these reference files.

![Voltage divider with optional output load](../images/voltage_divider.svg)

[Calculator](../calculators/voltage_divider.html) ·
[LTspice schematic](../ltspice/voltage_divider.asc)

## Circuit data

| Reference | Description | Default value | Positive node | Negative node |
| --- | --- | --- | --- | --- |
| V1 | Ideal DC source | 12 V | VIN | 0 (ground) |
| R1 | Upper divider resistor | 10 kΩ | VIN | VOUT |
| R2 | Lower divider resistor | 10 kΩ | VOUT | 0 (ground) |
| RL | Optional output load | Open; 100 kΩ when enabled in LTspice | VOUT | 0 (ground) |

R1 and R2 default to 1/4 W in the calculator. Power ratings and optional maximum
working voltages are analysis inputs; the ideal LTspice resistors do not model
rating limits or failure.

## Netlist

```spice
* Default unloaded divider
V1 VIN 0 DC 12
R1 VIN VOUT 10k
R2 VOUT 0 10k
* Optional load: uncomment to enable
* RL VOUT 0 100k
.op
.end
```

The `.asc` reference instead uses `LOAD_ON=0` and an RL resistance of 1e18 Ω to
approximate an open circuit. Set `LOAD_ON=1` to use the `RLOAD` parameter.

## Analysis

- `Rb = R2 || RL`, or `R2` when the load is open.
- `Vout = Vin × Rb / (R1 + Rb)`.
- `I1 = (Vin − Vout) / R1`; `I2 = Vout / R2`; `IL = Vout / RL` (zero for open load).
- Each resistor dissipates `P = I² × R`.
- Total dissipation is `P1 + P2 + PL = Vin × I1`.
- The unloaded Thevenin resistance is `Rth = R1 || R2`.

At the defaults, Vout is 6 V, I1 and I2 are 0.6 mA, and R1 and R2 each dissipate
3.6 mW. Total power is 7.2 mW and Rth is 5 kΩ.

## Solve modes

RTOP is R1 and RBOT is R2. The calculator can solve for VOUT, VIN, RTOP, RBOT,
or RL while the remaining nominal quantities are held at their entered values.
The calculated field is read-only and uses the selected resistance unit.

- VOUT uses the loaded divider equation above.
- `VIN = VOUT × (1 + RTOP / Rb)`.
- With `g = VOUT / VIN`, `RTOP = Rb × (1 − g) / g`.
- To solve a lower resistance, first calculate `Rb = RTOP × g / (1 − g)`.
- Unloaded: `RBOT = Rb`. Loaded: `RBOT = Rb / (1 − Rb / RL)`.
- To solve the load: `RL = Rb / (1 − Rb / RBOT)`.

Resistance solutions require the same sign for VIN and VOUT with
`0 < abs(VOUT) < abs(VIN)`. A passive load cannot increase the unloaded output
magnitude. The load solution is open circuit when the target equals the unloaded
output. Zero, negative, infinite, and otherwise infeasible resistance solutions
are rejected. Solved resistances are exact design values, not rounded to a
preferred component series.

## Tolerance analysis and solving

Independent VIN, R1, R2, and RL tolerances range from 0 to 99.999 percent. Each
input varies over `nominal ± abs(nominal) × tolerance / 100`. Defaults are ±1%
for R1/R2 and 0% for VIN/RL. Open loads ignore RL tolerance.

Minimum gain uses R1 high, R2 low, and RL low. Maximum gain uses R1 low, R2 high,
and RL high. Combining these gains with both VIN endpoints gives exact
worst-case VOUT bounds for the ideal resistive model, including negative sources.
Largest deviation is the larger endpoint distance from nominal VOUT, divided by
`abs(nominal VOUT)`. It is undefined for zero nominal output.

The **R1/R2 tolerance** solve mode finds the largest common independent tolerance
for both resistors that meets an entered VOUT error budget. VIN and RL tolerances
remain fixed inputs. Bisection searches from 0 to 99.999%; the result is rounded
down to six decimal places in percent. A nonzero nominal VOUT is required. A
budget already exceeded by VIN/RL variation with exact R1/R2 is rejected.

At the defaults, ±1% R1/R2 gives VOUT from 5.94 to 6.06 V. A ±5% output error
budget allows ±5% R1/R2 when VIN is exact and the load is open. Adding ±1% VIN
tolerance reduces that shared resistor allowance to approximately ±3.960396%.
These bounds apply to output voltage; displayed operating-point and stress
results continue to use nominal values.

## Stress definitions

| Result | Definition |
| --- | --- |
| Pstress | `P / Prated × 100%` |
| Vlimit | `√(Prated × R)`, capped by the entered maximum working voltage, if any |
| Ilimit | `Vlimit / R` (a derived limit, not an independent datasheet current rating) |
| Vstress | `abs(Vdrop) / Vlimit × 100%` |
| Istress | `abs(I) / Ilimit × 100%` |

The comparison uses common ratings of 1/16, 1/10, 1/8, 1/4, 1/2, 1, and 2 W.
At the defaults, each 1/4 W resistor has Pstress = 1.44%, Vstress = 12%, and
Istress = 12% when no maximum working voltage is entered.

Values above 100% exceed the applicable limit. With no maximum working voltage,
Vstress and Istress are power-equivalent calculations, not independent checks
against a component's actual voltage or current rating. The working voltage is
limited by both power and maximum working voltage; see
[Vishay's resistor technical guide](https://www.vishay.com/docs/49873/49873_sg2113.pdf).

The calculator uses nominal, positive, finite resistances and an ideal DC source.
Signed voltages and currents follow the positive-to-negative node directions
above; power and stress are nonnegative. Temperature derating, transients, and
independent datasheet current limits are not modeled. RL power is reported but
its rating is not evaluated.
