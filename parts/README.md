# Shared resistor parts

`index.json` lists the independently maintained family files and the supported
preferred-value series. `schema.json` documents the version 1 JSON format.
`../js/resistor-parts.js` loads, validates, builds, decodes, and suggests resistor
part numbers. The voltage divider and Part Number Radar both use this module.
No database, build step, supplier credentials, or third-party JavaScript is required.
Serve the repository over HTTP; JSON loading is not supported from `file://`.

## Supported catalogs and sources

| File | Scope | Primary source |
| --- | --- | --- |
| `resistors/vishay-eh-m55342.json` | Vishay E/H thin film, styles 01–12, solderable B termination, listed preferred values and supported ordering options | [Vishay 60018](https://www.vishay.com/docs/60018/eh.pdf), revision 2026-09-15, pp. 2–4 |
| `resistors/vishay-tnpw-e3.json` | TNPW e3 sizes 0201–1210; standard packaging and TCR/tolerance/range combinations; excludes TNPU and custom options | [Vishay 28758](https://www.vishay.com/docs/28758/tnpw_e3.pdf), revision 2026-04-10, pp. 1–4 |

All sources were checked on 2026-10-24. The value-series source is the
[Vishay standard resistance card](https://www.vishay.com/docs/49617/_color_code_card_draloric_resistors_vmn_ms6212_1501.pdf).
Military value-code interpretation is also documented by
[NASA NPSL](https://nepp.nasa.gov/npsl/Resistors/55342/55342pn.htm).
These catalogs are supported subsets, not exhaustive manufacturer inventories or
certification of a supplier's qualification, lot, screening, or current stock.

M55342 is a specification family used by multiple manufacturers; this file
specifically describes Vishay E/H. It must not be used for Vishay RCWPM thick-film
parts or another manufacturer's limits. Style /07 uses D55342. The RM0705 style
/06 is displayed with its 0805 footprint equivalence. The current E/H data uses
L = 200 ppm/°C and M = 300 ppm/°C, current case resistance limits, and the required
V suffix for K/L/M with tolerance ≥ 1%. Marking on small cases is excluded.
Preferred-value suggestions use E24/E96 for precision classes, E24 for 2%/5%,
and E12 for 10%; other/custom values are outside this implementation's scope.

Power values are condition-specific. E/H ratings are used at 70 °C, derated
linearly to zero at 150 °C. TNPW uses the datasheet's general, power, or advanced
P70 operating mode, derated from 70 °C to the mode's film-temperature limit.
0201 has no advanced mode. Terminal-temperature ratings are not substituted for
these P70 ratings. Suitable PCB thermal management remains a condition of use.
The calculator imports the allowed power at the chosen selection ambient and the
maximum working voltage; its normal stress equations apply both limits.
Selection ambient derates power only. TCR filters part numbers; temperature-induced
resistance drift and TCR tracking are not included in the divider's VMID bounds.

## Number validation and availability

- `rules-validated`: generated/decoded against this catalog's supported
  package, value series, range, tolerance, TCR, packaging, and suffix rules.
- `manufacturer-documented`: the exact number is also present in
  `verifiedParts`, with a source ID, page, and evidence type. An ordering or
  historical example is identified as such, not promoted to an active SKU.
- `stockStatus: "unknown"`, `stockCheckedAt: null`: no supplier stock or price
  check has been performed. Manufacturer documentation is not a stock claim.

Examples cannot bypass electrical validation. The E/H datasheet's illustrative
global-number example is not seeded as a verified part because its 1 MΩ value
exceeds the same revision's /06 range. Its valid historical 5.6 kΩ example is
retained with packaging unspecified. Generated packaged numbers do not inherit
that historical example's evidence. TNPW's exact 1.32 kΩ ordering example is
included with its own source reference.

Future supplier availability should be maintained separately, keyed by
manufacturer + exact MPN and supplier, with quantity, price/currency, packaging,
minimum order, source URL, and `checkedAt`. Consumers must check the timestamp
and display an unverified state when absent/stale. Do not add a permanent
`inStock: true` flag to a family rule or infer stock from a datasheet.

## Updating data

1. Check the manufacturer's current datasheet, including footnotes and ordering
   tables. Update a family file without editing calculator HTML.
2. Update the family `revision`, affected source revision, and `verifiedOn`.
   Keep dates distinct: catalog edits and datasheet publication are different.
3. Represent dependent combinations in `packages[].limits`, packaging restrictions,
   and suffix rules. Keep power modes and their reference temperatures explicit.
4. Add exact-number evidence only with a primary source and page. Specify whether
   it is an ordering example, historical example, or catalog entry.
5. For a new supported family, add a file and its entry in `index.json`. Existing
   `mil55342` and `rkm4` encodings can reuse the engine; a new numbering format
   needs an explicit, tested engine implementation. Add family-specific test
   coverage. The divider discovers manifest families automatically; an additional
   Radar family also needs its menu and decoder registration.
6. Validate with the schema, then run the browser checks below. Runtime loading
   checks references, numeric limits, code relationships, series, and examples.
   A failed catalog does not disable the divider's manual circuit analysis.
7. Follow the repository's append-only agent logging requirements for edits.

Unknown schema versions are rejected. Compatible data updates keep
`schemaVersion: 1`; incompatible structural changes require a new schema and a
corresponding engine update. Catalog fetches are shared within each page and
load fresh through normal HTTP caching on the next page load.

## API and verification

```js
const catalog = await ResistorParts.load();
const part = ResistorParts.evaluate(catalog, "vishay-tnpw-e3", {
  package: "0805", resistanceOhms: 10000, tolerancePct: 1,
  tcrCode: "E", packaging: "EA", mode: "general", temperatureC: 70
});
// TNPW080510K0FEEA, 0.14 W general P70, 150 V maximum working voltage.
const decoded = ResistorParts.decode(catalog, part.familyId, part.mpn);
const matches = ResistorParts.suggest(catalog, part.familyId, {
  package: "0805", resistanceOhms: 2500, maxTolerancePct: 1,
  tcrCode: "E", packaging: "EA", mode: "general", temperatureC: 70
});
const allValues = ResistorParts.enumerate(catalog, part.familyId, {
  package: "0805", tolerancePct: 1, minOhms: 1000, maxOhms: 100000,
  tcrCode: "E", packaging: "EA", mode: "general", temperatureC: 70
});
```

`enumerate()` returns every supported preferred value in an inclusive resistance
range at one exact catalog tolerance and ordering/operating configuration. It
clips generation to the family's applicable electrical ranges, deduplicates
overlapping preferred series, and validates every result through `evaluate()`.
It has no nearest-value window or result-count limit. The divider's pair search
uses this API for both arms, then filters combinations by target VMID bounds and
worst-case stress/power. Pair-search UI, chart, and circuit criteria remain in the
calculator HTML; the shared engine remains independent of circuit topology.

`suggest()` defaults to ±5% resistance deviation and returns nearest supported
values. The caller must recalculate its actual circuit before accepting a part;
the shared module has no knowledge of a divider's topology. The divider previews
VMID, tolerance bounds, and selected-part stress, applies one physical part at a
time, and switches to forward VMID analysis so inverse solving cannot overwrite
the chosen catalog value. Applied MPNs appear in the live SVG and resistor CSV
BOM. Editing a chosen part's resistance, tolerance, rating, or voltage limit
removes its MPN association. Unassigned BOM rows are labeled explicitly.

From a local HTTP server rooted at the repository, open:

- [Catalog, divider integration, and Radar checks](../calculators/tests/resistor_parts.html)
- [Existing divider regression checks](../calculators/tests/voltage_divider.html)
- [Complete resistor-pair search and chart checks](../calculators/tests/resistor_pairs.html)

The first suite tests source examples, numbering round trips, package/TCR/range
exclusions, derating, malformed data, candidate application, multi-part networks,
CSV/SVG output, Radar integration, responsive layout, and missing-module fallback.
