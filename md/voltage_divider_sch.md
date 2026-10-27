# Voltage Divider — Schematic Export (Markdown)

miniPCB · Circuit boards for electronics education

This hand-authored reference describes the calculator's ideal DC circuit; it is
not an EAGLE board export. The downloadable LTspice file contains the default
values below. Calculator edits do not modify these reference files.

After circuit edits or resistor-pair searches, leaving, refreshing or closing the
page requests the browser's standard confirmation so you can stay and keep your
work. This includes changes made through the SVG and unfinished SVG edits.
Restoring the original circuit and search defaults clears the warning when no
search results or assigned parts remain. Switching result tabs, copying tables
and downloading files keep your work on the page. Circuit data is not saved
between visits; the browser controls the warning text and requires prior user
interaction before showing it.

Right-click a physical RTOP/RBOT resistor in the live SVG to add a resistor in
**series** with it or in **parallel** across it. Focus the resistor and press
**Shift+F10** for the same menu; arrow keys select an action and Escape closes
it. Additions apply to that resistor, so an arm can contain nested series and
parallel branches. The drawing, equivalent resistance, per-part currents,
powers, tolerance limits, stresses and BOM use that actual connection tree.
The work form shows **Mixed · follow schematic** for a mixed arm; choosing
Series chain or Parallel bank reconnects every resistor in that arm accordingly.
Remove prunes the selected resistor and collapses one-member branches. Pair
searches continue to use one resistor per arm; apply a pair before editing its
construction.

New resistors default to **undefined automatic values**. Existing entered values
stay fixed. The **Choose resistor values** form lets you set target VMID, a
preferred nominal error, catalog family, footprint, TCR and starting RTOP + RBOT.
Each physical resistor retains its own tolerance selection. Use the context menu
or each part's checkbox to mark other resistances automatic; **Make all resistors
automatic** includes both arms. Select one automatic resistor as the **ratio
trim**. **Keep the current value fixed** converts a chosen value into an input.

The first picking rule seeks similar **nominal dissipated power** across all
non-trim RTOP/RBOT resistors, including fixed resistors. It samples power scales and
refines discrete catalog choices, then inverts the trim resistor's connection
path and checks neighboring catalog values to approach the requested divider
ratio. It prefers results inside the nominal error band and then lower power
spread; if no searched candidate meets the band, it reports the closest result
found and labels it **outside preferred band**. The spread is the non-trim
maximum minus minimum power, divided by their mean. Starting resistance sets
the initial scale and breaks otherwise equivalent choices; it is not a hard
total-resistance constraint. The search is bounded, not exhaustive or a proof of
the globally best catalog combination.

Automatic choices use the shared TNPW or M55342-family catalog and its supported
ordering rules at 70 °C. The chosen footprint determines power/voltage limits;
nominal per-part stress must remain within those limits. Source/load and
component tolerances remain part of the circuit analysis; the preferred design
band is nominal, unlike the existing real-pair search's worst-case band. Review
the resulting tolerance interval and stresses. Supplier stock is not checked.
Actual selected values and MPNs appear in the SVG and copied BOM; the resistance
input remains blank with its chosen value as a placeholder to distinguish an
automatic value from a fixed input. Edits invalidate old choices and clear stale
analysis until values are chosen again. Switching Find modes fixes already
chosen resistances before the ordinary solver runs. Reset defaults clears
construction, automatic roles and chosen parts. SVG downloads preserve the
connection drawing as a static snapshot.

The calculation choices appear above the live circuit SVG. Each choice lists
**Given** inputs and the value to **Find**; the form and diagram use the same
**Find** wording. The SVG updates VTOP, VMID, the equivalent arm resistances,
and the open/finite RL value as you edit.
Voltage readouts are part of the circuit drawing: VTOP and source tolerance sit
beside the source, and VMID sits at the end of a blue output wire extending just
past the RL branch. A separate, spaced VMID readout lists **Nominal**, **Min** and
**Max** voltages for both normal calculations and pair previews. Its minimum and
maximum use the same entered tolerance limits as the analysis results; pair
previews also show their target error. Invalid circuit data clears all three
values. Calculated voltages are read-only; an entered VMID target remains editable
in inverse modes. The readouts retain their role colors and appear in the
standalone SVG download.
Each physical RTOP/RBOT resistor is annotated with its resistance, tolerance,
footprint size, power rating, Pstress, Vstress, and Istress. The drawing contains
one symbol per physical RTOP/RBOT resistor in the work form, wired as a series
chain or a parallel bank. A finite RL adds its load symbol; an open RL has no
resistor symbol. Each drawn part shows its value and two small filled pills for
tolerance (for example, **±1%**) and package size (for example, **0805**), without
repeating Tol. or Footprint labels. The pills have no outlines and their entire
area is clickable and keyboard accessible; hover/focus identifies the control.
Accessible labels and reference tooltips retain the full parameter names.
Manual packages read **Not set**, since package size cannot be inferred from
power. Equivalent arm labels allow total-resistance editing when that arm is an
input; calculated arm values are read-only.
VTOP, RL and every physical resistor have rounded, borderless information boxes
matching the VMID readout. Parallel-bank boxes keep the resistor symbols and
connections visible. The **Parts list and electrical part stress** table contains **Ref Des**,
**Description**, **TNPW PN**, **M55342 PN**, **Pstress**, **Vstress** and **Istress**
columns and one row per physical resistor. The description shows actual resistance,
tolerance and footprint; unassigned footprints read **Footprint not set**. On
smaller screens, each reference and description sit above the part-number and
stress cells so the table stays readable without horizontal scrolling.
An asterisk marks the selected
part number; stress uses the current circuit or preview part's own ratings.
A dash means no assigned or qualifying part number for that family. Click a
reference to edit the resistor and its catalog options. Reference tooltips retain
value, tolerance, footprint and rating; part-number tooltips retain each family's
independent limits and conditions. The table is included in Download SVG.
Ratings are not combined. Stress
values use the nominal operating point and include each part's working-voltage
limit when entered. Invalid circuit data clears the live values and stresses.

The components use **yellow** for missing/invalid inputs or an unspecified
footprint, **green** for known information, and **red** for the value to find.
A **Find** heading and target labels identify the active calculation without relying on
color; known components omit repeated status labels. The selected calculation,
form inputs and result use the same cues; a calculated value stays red to identify
its role. A blank optional RL is a known open circuit. Multi-part arms highlight
all resistors being scaled. Pair previews highlight the candidate RTOP/RBOT in
red. Without a selected pair, the diagram shows pair-search inputs and unknown
resistor values instead of the applied circuit.
Stress colors continue to describe rating limits independently of input roles.

Part-number tooltips include resistance alongside the part's operating limits;
both graph hover readouts also show the resistance of each part. The **Copy BOM**
pill below the SVG parts table copies the displayed physical resistors as a
spreadsheet-ready table, including quantity, resistance, tolerance, footprint,
selected part number, both family part numbers and nominal P/V/I stress. In pair
mode it copies the preview without applying it to the circuit. If clipboard
access is unavailable, the text is selected below the diagram for manual copying.

The SVG BOM shows exact resistance/tolerance matches even before a catalog part
has been applied. Unassigned parts use the package, ambient and TCR selected in
**Parts (2)** for suggestions; assigned parts retain their own package and
conditions. If a family has no exact match, its cell shows an amber **Nearest**
recommendation with the proposed resistance, signed percentage change, tolerance
and footprint. Unsupported tolerances are visibly labeled **Tolerance change**.
The nearest resistance uses the current tolerance where supported. Otherwise,
the closest supported tighter tolerance is preferred; a looser tolerance is shown
only when no tighter option exists.

**Use** adopts that one physical resistor's resistance, tolerance, footprint,
power rating, working-voltage limit and real part number, then recalculates the
circuit and BOM while preserving the active Find mode. Calculated Find values
remain read-only. Over-rating or infeasible recommendations cannot be applied;
their tooltip shows the candidate's limits and preview result or reason.
In pair mode, suggestions come from validated visible pairs with the other
resistor unchanged. **Preview** selects that pair; **Apply pair** remains the
explicit step that transfers it to the circuit.

**Copy BOM** includes the description and assignment status. Exact matches appear
in the family PN columns; nearby-value or different-tolerance proposals appear
in separate **recommendation (not applied)** columns, preserving the actual
values and selected PN until adoption. Static SVG downloads keep descriptions
and recommendation labels while removing live adoption controls.

Click an underlined SVG value or a pill, or focus it and press Enter/Space, to
edit the circuit. VTOP opens voltage and source tolerance; RL opens resistance and load
tolerance (blank resistance means open circuit). Each physical resistor opens
its resistance and dropdowns for family, footprint, TCR (ppm/°C), tolerance and
reliability level. M55342 offers the catalog reliability codes; TNPW displays
**Not applicable**. Footprint, TCR and tolerance choices follow the selected
family's supported combinations. A live part-number preview shows the result.

Power is read-only in the SVG editor and follows the selected catalog part's
footprint, operating mode and ambient derating. Catalog working-voltage limits
also update automatically. Saving applies the validated part number, tolerance,
power and voltage limits to the circuit and BOM. Unsupported exact values and
parts exceeding nominal power/voltage limits cannot be applied. Existing catalog
parts reopen with their reliability, TCR, tolerance, footprint and conditions.

For an unassigned resistor, **Manual · keep current limits** preserves its current
power rating and offers a tolerance dropdown and optional working-voltage input.
Choose a family to enable catalog footprint, TCR and reliability choices. Manual
mode permits custom values and clears a prior catalog assignment when explicitly
selected. Source/load tolerances retain numeric entry. Saving updates the existing
forms and recalculates the selected result and stress while preserving the active
Find mode. Cancel or Escape leaves the circuit unchanged.

In inverse modes, click VMID to edit the entered target and choose whether VTOP,
RTOP, RBOT or RL should be found. Every value in the Find state has no edit link
or keyboard button, including individual resistances in a calculated multi-part
arm. Other specification editors keep calculated values and units read-only;
calculated tolerance selections are disabled in tolerance analysis. Known inputs
remain editable, and their changes recalculate the selected result.
For a multi-resistor input arm, clicking its equivalent value or connection
opens an editor that scales all part resistances together for the requested
equivalent and series/parallel connection, preserving independent ratings and
tolerances. Individual SVG rows edit just that physical resistor. Invalid edits
remain in the editor with an error and leave the applied circuit unchanged.

The SVG reflows for smaller screens and stays on the calculator page.
**Download SVG** captures the current annotations in a standalone SVG. The image
below and the LTspice/Markdown downloads remain the default circuit references;
the calculator keeps its live SVG, editor, styling, and logic in the one HTML
file. Downloads are static annotated images without calculator editing controls.

In the resistor-pair visualization, selecting a point or table row previews that
pair in the top SVG, including VMID bounds, error, power, current, Rth and worst
stress. The per-part fields show the selected MPN's nominal stress. Matching
TNPW or M55342/D55342 alternatives appear alongside it with their own power and
voltage limits. Preview alternatives must also satisfy the pair search criteria;
other calculator views check alternatives at the nominal operating point.
Selecting a candidate preserves the applied circuit inputs and BOM. The heading
identifies the preview, and Download SVG captures it. Leaving the visualization
or selecting an empty region restores the pair-search input display.

The common **Circuit characteristics** table appears in every Find mode, beside
the circuit on larger screens and above it on smaller screens. It identifies the
calculated quantity and lists nominal total power, input current and source
resistance Rth. Ordinary modes show the highest nominal Pstress and V/I stress
among all physical RTOP/RBOT parts; pair previews retain their validated worst-case
stress values. Find RL also shows load power; tolerance analysis shows the found
per-resistor tolerance and allowed VMID error.

Where an independent VMID target exists (inverse modes and pair searches),
**Nominal target error** is the absolute output error divided by the target
magnitude, expressed as a percentage; **0%** means on target. **Worst target
error** uses the full minimum/maximum VMID interval. Pair searches also show the
allowed error. Find VMID instead shows **VMID accuracy**, the worst tolerance
deviation about its nominal result, without inventing a target. Zero targets and
zero nominal VMID use voltage error/variation because relative percent is undefined.
After adopting a nearby catalog part, Find VMID retains the original nominal
VMID as its reference and shows the resulting target error. Applying a resistor
pair retains that search's requested VMID target. A manual circuit edit clears
the saved reference, returning to the nominal tolerance band.

The **Analyzed** row records the successful circuit calculation or completed pair
search date and time in UTC. Filtering, resizing or choosing another pair keeps
that timestamp; recalculating the circuit or running a new search records a new
one. Missing/invalid inputs and pair setup keep the common table while clearing
unavailable or stale results. The **Calculator** link opens the voltage divider
page. The table, timestamp and link remain in the downloaded SVG in every mode.

The SVG also sets up the pair search before any results exist. Click VTOP for the
source and its tolerance, the separate **Target** row for VMID and its allowed
error, or RL for the optional load and its tolerance. Click a resistor reference,
tolerance pill or package pill to choose that arm's family, package and exact
catalog tolerance. These editors also offer the shared TCR requirement.
The SVG's **Options** control opens the resistance range, ambient temperature,
shared TCR, maximum stress and optional total-power limit. **Find pairs** runs the
search directly from the diagram. All these controls use the same settings and
validation as the pair-search form, including when the applied circuit is invalid.

The pair diagram keeps entered targets separate from candidate nominal/min/max
results. Resistor values and nominal performance are read-only. Saving an SVG
search edit synchronizes the pair form and searches again; it does not apply a
candidate or change the circuit/BOM. Canceling, invalid edits and stale editors
preserve the current settings and applied circuit. A search with no matches clears
old candidate annotations and leaves its inputs editable. Use the existing
**Apply** action to transfer a chosen pair into the circuit and BOM.

Below the circuit, the same SVG contains a **Pair performance** explorer. Six
two-ended sliders filter total power, input current, output Rth, target error,
Pstress and V/I stress. Power/current/Rth are nominal; error/stress use the
validated worst-case tolerance intervals. Positive power, current and Rth ranges
use logarithmic interpolation. The slider domains stay at the full search range
so filtered-out values can be restored. Sliders, numeric chart bounds, family
toggles, result rows and filtered CSV share one result selection; filters across
different metrics intersect. Axis changes clear the old coordinate bounds while
retaining other performance filters. Clear filters restores every range/family.

Two native SVG scatter plots show actual part-number combinations, with both axes
rescaled to the currently filtered pairs. The first uses the detailed chart's
selectable axes; the second plots Rth against Pstress. Disabled families and
filtered-out pairs are omitted. Hover shows both full part numbers separately
from the selected combination. Click a point to update the circuit preview and
table selection; clicking overlapping points cycles their actual combinations.
Dragging either plot adds its data-space bounds to the shared filters.

**Axes**, **View table**, **Compare pair**, **Copy comparison** and **Apply pair**
are available beside the plots. Comparison membership survives performance
filtering, and copying uses the existing standard comparison table and its column
and performance filters. Only Apply changes the circuit/BOM. Controls reflow on
small screens and support mouse, touch and keyboard. Slider arrows change the
range; PageUp/PageDown use larger steps, Home/End reach the endpoints, and Escape
cancels a drag or clears filters. Plot arrows select real combinations and Enter
toggles their comparison membership. The standalone SVG retains native plots,
selected part numbers and range annotations with live controls removed.

![Voltage divider with optional output load](../images/voltage_divider.svg)

[Calculator](../calculators/voltage_divider.html) ·
[LTspice schematic](../ltspice/voltage_divider.asc)

## Circuit data

VTOP is the source voltage at the top of RTOP. VMID is the midpoint voltage
between RTOP and RBOT. Both voltages are measured relative to ground.

| Reference | Description | Default value | Positive node | Negative node |
| --- | --- | --- | --- | --- |
| V1 | Ideal DC source | 12 V | VTOP | 0 (ground) |
| R1 | Upper divider resistor | 10 kΩ | VTOP | VMID |
| R2 | Lower divider resistor | 10 kΩ | VMID | 0 (ground) |
| RL | Optional output load | Open; 100 kΩ when enabled in LTspice | VMID | 0 (ground) |

R1 and R2 default to 1/4 W in the calculator. Power ratings and optional maximum
working voltages are analysis inputs; the ideal LTspice resistors do not model
rating limits or failure.

## Netlist

```spice
* Default unloaded divider
V1 VTOP 0 DC 12
R1 VTOP VMID 10k
R2 VMID 0 10k
* Optional load: uncomment to enable
* RL VMID 0 100k
.op
.end
```

The `.asc` reference instead uses `LOAD_ON=0` and an RL resistance of 1e18 Ω to
approximate an open circuit. Set `LOAD_ON=1` to use the `RLOAD` parameter.

## Analysis

- `Rb = R2 || RL`, or `R2` when the load is open.
- `VMID = VTOP × Rb / (R1 + Rb)`.
- `I1 = (VTOP − VMID) / R1`; `I2 = VMID / R2`; `IL = VMID / RL` (zero for open load).
- Each resistor dissipates `P = I² × R`.
- Total dissipation is `P1 + P2 + PL = VTOP × I1`.
- The unloaded Thevenin resistance is `Rth = R1 || R2`.

At the defaults, VMID is 6 V, I1 and I2 are 0.6 mA, and R1 and R2 each dissipate
3.6 mW. Total power is 7.2 mW and Rth is 5 kΩ.

## Solve modes

RTOP is R1 and RBOT is R2. The calculator can solve for VMID, VTOP, RTOP, RBOT,
or RL while the remaining nominal quantities are held at their entered values.
Choose a calculation button at the top of the page. The sixth button,
**Find real resistor pairs**, searches actual catalog parts for a target VMID.
Each circuit-analysis view names the goal, explains its inputs, and shows a
matching equation and Calculate action. Only known quantities appear as primary
inputs; the calculated quantity appears in the result banner. Switching views
preserves circuit data.

The result area uses **Overview**, **Tolerances**, **Stress**,
**Ratings**, **Parts**, **Parts (2)**, **Resistor pairs**, and **Method** tabs to show
one focused panel at a time.
The solved value stays visible above the tabs; all results continue updating as
you edit. Switching result tabs preserves circuit data and selected parts.
Pair searches open **Resistor pairs**; circuit calculation choices open
**Overview**. The Calculate action opens the relevant result view, and Reset
restores **Overview**. Use Left/Right Arrow, Home, or End to navigate the tabs
with a keyboard. Printing includes all result panels.

Output load and tolerance/rating settings are collapsible. Pair searches have
their own target and tolerance form. An invalid setting automatically opens its
containing sections so it can be corrected. The page styling and circuit-analysis
logic remain in the one HTML file; shared part catalogs and their numbering
engine are loaded separately.

- VMID uses the loaded divider equation above.
- `VTOP = VMID × (1 + RTOP / Rb)`.
- With `g = VMID / VTOP`, `RTOP = Rb × (1 − g) / g`.
- To solve a lower resistance, first calculate `Rb = RTOP × g / (1 − g)`.
- Unloaded: `RBOT = Rb`. Loaded: `RBOT = Rb / (1 − Rb / RL)`.
- To solve the load: `RL = Rb / (1 − Rb / RBOT)`.

Resistance solutions require the same sign for VTOP and VMID with
`0 < abs(VMID) < abs(VTOP)`. A passive load cannot increase the unloaded output
magnitude. The load solution is open circuit when the target equals the unloaded
output. Zero, negative, infinite, and otherwise infeasible resistance solutions
are rejected. Solved resistances are exact design values, not rounded to a
preferred component series.

## Multiple physical resistors per arm

Open **RTOP parts** or **RBOT parts** and enable **Use multiple resistors** to
replace that single resistor with a series chain or parallel bank. When solving
for an arm, its construction settings remain available below the known inputs.
Each physical part has its own resistance/unit, power rating in watts,
tolerance, and optional maximum working
voltage. Each part has a compact resistance/rating/tolerance summary that opens
for editing; adding a part opens it, while the four-part shortcut initially
opens only the first part. Add/remove controls keep at least one part in an
active arm. The two arms may use different connection types; nested
series/parallel networks are not supported.

The **Split into 4 equal parts** shortcut is available for a one-part arm. It
preserves nominal equivalent resistance: each series part becomes one quarter
of the original resistance; each parallel part becomes four times the original.
New parts copy the existing part's rating, tolerance, and working-voltage input.
Edit those values for your selected components. A package such as 0805 does not
uniquely specify power, tolerance, or working voltage.

- Series: `Rarm = sum(Ri)`, `Ii = Iarm`, `Vi = Iarm × Ri`.
- Parallel: `Rarm = 1 / sum(1 / Ri)`, `Vi = Varm`, `Ii = Varm / Ri`.
- Each physical part dissipates `Pi = Vi × Ii`; its stress uses its own rating.
- Part powers sum to arm dissipation. Displayed arm totals already include their
  parts; the total circuit power does not count them twice.

The arm resistance and equivalent tolerance become calculated fields. Single
resistor rating/working-voltage controls are replaced by the per-part controls.
Power ratings are never pooled into a combined rating that could hide an
overloaded part. The common-rating comparison lets you choose one physical part
from each arm and includes custom power ratings entered for the selected parts.

Solving RTOP or RBOT scales all its physical resistances by the same factor,
preserving their ratios and each part's entered rating and tolerance. This is a
proportional design solution, not a search for standard resistor values. Parts
and their ratios remain available after an infeasible target so it can be fixed.
Turning an arm back to a single resistor retains the equivalent nominal value;
re-enabling the network restores its part list. Reset removes all networks.

For example, RTOP can be four 2.5 kΩ series resistors with RBOT = 10 kΩ and
VTOP = 12 V. Each upper part then drops 1.5 V, carries 0.6 mA, and dissipates
0.9 mW. If each is entered as 0.125 W, its Pstress is 0.72%. The 0.125 W value is
an example input, not a rating assigned to all 0805 components. Four 40 kΩ parts
in parallel give the same 10 kΩ arm, with 6 V and 0.15 mA per upper part.

## Tolerance analysis

Independent VTOP, R1, R2, and RL tolerances range from 0 to 99.999 percent. Each
input varies over `nominal ± abs(nominal) × tolerance / 100`. Defaults are ±1%
for R1/R2 and 0% for VTOP/RL. Open loads ignore RL tolerance.

Minimum gain uses R1 high, R2 low, and RL low. Maximum gain uses R1 low, R2 high,
and RL high. Combining these gains with both VTOP endpoints gives exact
worst-case VMID bounds for the ideal resistive model, including negative sources.
Largest deviation is the larger endpoint distance from nominal VMID, divided by
`abs(nominal VMID)`. It is undefined for zero nominal output.

At the defaults, ±1% R1/R2 gives VMID from 5.94 to 6.06 V. A ±5% output error
band around a 6 V target therefore includes that divider. The pair search checks
the full interval against the target band, including any nominal output mismatch.
The other operating-point and stress tabs continue to use nominal values.

For multiple-part arms, the minimum/maximum equivalent resistance is evaluated
using every physical part's own lower/upper resistance limit. Series endpoints
sum; parallel endpoints use the reciprocal conductance sum. Unequal parallel
tolerances can produce an asymmetric interval around nominal resistance. The
equivalent tolerance field reports the larger relative deviation, while the
output calculation uses the actual asymmetric interval. Tolerance tables show
both arm intervals and the individual part intervals.

These are independent worst-case limits, not a statistical average: four equal
1% parts still allow a 1% equivalent arm excursion when they all vary together
in the same direction. Manual multi-part stress analysis uses nominal per-part
voltages and currents; the two-resistor pair search additionally checks worst-case
power and voltage across its selected source, resistor, and load intervals.

## Finding real resistor pairs

Choose **Given VTOP, VMID, tolerances → Find real resistor pairs**. Enter VTOP,
its tolerance, target VMID, allowed target error, and the exact catalog tolerance
for each resistor. The source and target must have the same sign, with
`0 < abs(VMID) < abs(VTOP)`. The search uses one catalog resistor per arm.

Optional settings choose the family and package independently for RTOP and RBOT,
an inclusive resistance range for both arms, load/tolerance, ambient, TCR, maximum
stress, and maximum total power. Defaults search both catalog families, 0805,
1 kΩ–100 kΩ, ±1% resistors, 70 °C, and 25 ppm/°C, with an open load. Family default
power modes, failure-rate levels, and package-compatible packing apply. These
settings define the complete search space; unsupported or custom catalog values,
other ordering variants, temperature drift, and multi-part networks are outside
this pair search. The existing manual multi-part calculator remains available.

**Find resistor pairs** enumerates every supported preferred value in the chosen
range, validates real part numbers through the shared catalog engine, and checks
same-family and mixed-family pairs. A combination qualifies only when its entire
VMID interval lies within `target ± abs(target) × allowed error / 100`, and both
parts meet the selected stress limit. This includes nominal ratio error, source
tolerance, each resistor's actual tolerance, and finite-load tolerance.

Worst-case power uses the maximum source magnitude and the resistor/load bounds.
It also checks interior maximum-power points: RTOP matched to the minimum loaded
bottom resistance, and RBOT matched to `RTOP_min || RL_max` (or RTOP_min with no
load). Worst voltage uses the appropriate monotonic endpoints. V/I stress follows
the existing power-derived limit capped by the part's working voltage; independent
datasheet current limits are not modeled. Total-power limits include RL, whose
rating is not checked. Catalog ambient derates allowable power; TCR filters codes.

All matches appear on the interactive scatter chart. Choose power, input current,
or unloaded output resistance Rth for the logarithmic X axis; compare worst target
error, nominal error/VMID, or worst P/V/I stress on Y. Points can overlap when
different part numbers have the same performance. Hover to inspect a point,
or select a point/table row to preview its pair in the top SVG. Sorting applies
to all matching results; table pages show 50 visible combinations at a time. **Download all
combinations CSV** includes every match, its conditions, source links, and nominal
and worst-case performance. Supplier stock remains unverified.

Click and drag a rectangle over the chart to show only pairs inside that area in
the table. Dragging in any direction replaces the previous area. Points outside
the bounds remain dimmed as context. The **TNPW / TNPW**, **M55342 / M55342** and
**Mixed families** legend checkboxes independently control which combinations
appear in the chart, table and filtered CSV. All three start selected; unchecking
all three leaves an empty chart and table. Unselected families are hidden entirely.
**Filter bounds** offers equivalent numeric limits in the displayed axis units.
Numeric bounds and selected families intersect. Axis changes clear coordinate
bounds and retain selected families; resizing keeps the selected data range.
**Clear filters** restores all matches and enables all three families. With the chart
focused, Escape cancels an unfinished drag, or clears all filters when no drag
is active.

Counts, table sorting and pagination follow the visible subset. If the current
pair is excluded, the first remaining pair is previewed; an empty selection
clears the preview and disables applying or exporting a filtered pair set.
**Download filtered CSV** includes exactly the visible pairs, while **Download
all combinations CSV** preserves the full search. Filters do not rerun the
catalog search. Editing search inputs or resetting the search clears filters
and stale results together.

Use a result row's **Compare** checkbox to select multiple pairs for the
**Compare resistor pairs** table below the results. **Add preview to comparison**
also adds the currently previewed chart/table pair. **Preview** continues to
choose the pair displayed in the top SVG; adding a comparison leaves the applied
circuit and BOM unchanged. Pairs are kept in selection order without duplicates
across pages, sorting, axis changes and chart/family filters. The count identifies
selected pairs outside the current chart filters. Uncheck a pair, use its
**Remove** button, or **Clear comparison** to remove selections. Starting a new
search, editing its inputs or resetting/canceling it clears stale comparisons.

Each selected option has two standard BOM rows, one for RTOP and one for RBOT,
with option number, reference, quantity, value, tolerance, actual footprint and
manufacturer part number. VMID is shown by default. **Columns and performance
filters** adds individual ratings, TCR/reliability, operating-point values,
worst per-part stresses, divider statistics, search conditions or alternate-family
numbers. Numeric filters apply maximum worst Pstress, V/I stress and worst total
power to complete options; a part-number/text match keeps both resistors together.
These table filters preserve the comparison selections. **Clear table filters**
restores rows while retaining the chosen columns.

**Copy table** copies only visible physical rows and selected columns as
tab-separated text for a spreadsheet or document. Enable **Search conditions**
to include the source, target, load and ambient in the copied table. If clipboard
access is unavailable, the page selects the complete text for manual copying.
Changing the selected comparison clears outdated copy text.

**Apply selected pair** sets both actual resistor values and ratings together,
copies the search's source/load conditions, and switches to forward VMID analysis.
It opens the Parts (2) BOM with both MPNs and updates the live SVG. Applying a pair
selects single-resistor arms; retained manual network editors can be re-enabled.
Changing search settings clears stale results, export, and application. **Cancel**
discards incomplete results, and **Reset search** restores the search defaults.

## Selecting actual resistor part numbers

Open the **Parts** tab. **Choose real resistor parts** uses the shared
[parts catalog](../parts/README.md)
for Vishay E/H M55342/D55342 and TNPW e3. Choose a physical resistor, family,
package, and tolerance ceiling. The optional settings specify TCR, packaging,
failure-rate level where applicable, power operating mode, and selection ambient.
Defaults use 70 °C and TNPW general operation. These are sourced, supported family
subsets, not an exhaustive inventory or a live supplier stock search.
Selection ambient adjusts allowed power; TCR filters part numbers. Temperature
drift and TCR tracking are not included in the VMID tolerance bounds.

Suggestions are preferred values within ±5% of the target physical resistance.
Each preview recalculates the actual arm equivalents, VMID, tolerance bounds,
and selected-part stress with the candidate's working voltage and allowed power
at the chosen ambient. Candidates exceeding the selected part's nominal limits
are omitted. Other parts' limits remain visible in the normal circuit results;
matching one resistor does not guarantee a complete design meets its targets.

Applying a part fixes its actual resistance, tolerance, allowed power, and working
voltage and switches to forward VMID analysis. This prevents an inverse solver
from replacing the chosen catalog value with an ideal value. Apply each physical
part separately; parts can come from different families. Applied MPNs appear in
the live SVG and **Download resistor BOM** exports the physical part list,
ratings/conditions, source, and validation status as CSV. Unassigned parts are
explicitly labeled. Manual changes to a part's resistance, tolerance, power, or
working voltage remove its MPN association; reset clears all associations.

Generated numbers are **rules validated**. An exact sourced example is
**manufacturer documented**, with its evidence type recorded in the catalog.
Neither status means **in stock**; supplier availability remains unverified.
Catalog JSON updates are independent of calculator HTML and are also consumed
by Part Number Radar. See the catalog README for schema, sources, scope, and
maintenance instructions.

### Parts (2): value table and copyable BOM

The **Parts (2)** tab presents selectable resistance/tolerance rows with TNPW
and M55342/D55342 part numbers side by side. Choose the physical resistor,
package size, tolerance ceiling, and family to apply. Click a row (or use its
radio button) to preview VMID and its tolerance bounds, then apply the selected
family's part. Selection alone does not modify the circuit. Both Parts tabs
share the same applied assignments, live schematic, and CSV export.
The candidate list scrolls with fixed column headings so the BOM remains nearby;
on smaller screens, scroll either table horizontally to see the family columns.

This comparison uses each family's default power mode, package-compatible
packing, and M55342 failure-rate level. Ambient and TCR can be selected;
the original **Parts** tab retains the other ordering/power-mode controls.
Rows align the same resistance, tolerance, size, and TCR. Each family retains
its own allowed power and working-voltage limit. A dash means no supported match
meets the selected family rules and selected-part nominal stress limits.

The **Circuit BOM** starts with standard reference, quantity, value, tolerance,
footprint and manufacturer-part-number columns, with one row per physical
RTOP/RBOT resistor. Unassigned parts show **Unassigned** and **Not set** for the
MPN and footprint. **Columns and performance filters** can add ratings,
TCR/reliability, part voltage/current/power, nominal P/V/I stress, conditions and
both exact-value family alternatives. Text search and maximum nominal Pstress,
V/I stress and per-part power narrow the visible rows without changing the circuit.
Clear table filters restores all rows; column choices persist.

Applied parts retain their actual package, ambient, TCR and mode when catalog
comparison settings change. Alternatives use those conditions where available
and the other family's default mode. Previously applied parts remain identified
when later edits exceed their ratings; optional stress columns show the result.

**Copy BOM** copies the visible standard/optional columns and filtered physical
rows as tab-separated text. The original resistor BOM CSV retains the complete
applied-circuit export. If clipboard access is unavailable, a text area opens
with the visible BOM selected for manual copying. Invalid circuit
data clears the BOM; manual part edits and reset clear stale assignments.

## Stress definitions

| Result | Definition |
| --- | --- |
| Pstress | `P / Prated × 100%` |
| Vlimit | `√(Prated × R)`, capped by the entered maximum working voltage, if any |
| Ilimit | `Vlimit / R` (a derived limit, not an independent datasheet current rating) |
| Vstress | `abs(Vdrop) / Vlimit × 100%` |
| Istress | `abs(I) / Ilimit × 100%` |

The comparison and single-resistor selectors offer 15 presets: 0.03, 0.05,
0.0625, 0.1, 0.125, 0.25, 0.5, 0.75, 1, 2, 3, 5, 10, 25, and 50 W.
Per-part custom ratings are also supported. For manufacturer examples, see the
[Bourns chip resistor guide](https://www.bourns.com/docs/technical-documents/technical-library/fixed-resistors/publications/bourns_chip_resistors_arrays_sf.pdf)
and [Vishay RH/NH power resistor datasheet](https://www.vishay.com/docs/30201/rhnh.pdf).
Use the actual component's rating for its temperature and mounting; some
high-power ratings require a specified heat sink.

At the defaults, each 1/4 W resistor has Pstress = 1.44%, Vstress = 12%, and
Istress = 12% when no maximum working voltage is entered.

Values above 100% exceed the applicable limit. With no maximum working voltage,
Vstress and Istress are power-equivalent calculations, not independent checks
against a component's actual voltage or current rating. The working voltage is
limited by both power and maximum working voltage; see
[Vishay's resistor technical guide](https://www.vishay.com/docs/49873/49873_sg2113.pdf).

The calculator uses nominal, positive, finite resistances and an ideal DC source.
Signed voltages and currents follow the positive-to-negative node directions
above; power and stress are nonnegative. Catalog selections import power derated
for their selected ambient; manual ratings are used as entered. Transients and
independent datasheet current limits are not modeled. RL power is reported but
its rating is not evaluated.
