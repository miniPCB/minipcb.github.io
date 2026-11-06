# Calculator notes for AI agents

These are established miniPCB calculator conventions. Preserve them when making
changes to calculator pages, shared JavaScript, schematics and exports. They do
not add a permission or confirmation step to an authorized task.

## Schematic drawing

- Use blue `#54d2ff` for ordinary nets, including internal connections and ground.
  Never use grey for electrical wiring. Neutral text and UI borders may stay grey.
- A calculated voltage net uses red: VMID in Find VMID, VTOP in Find VTOP.
  Keep an entire net, its branches, junction dots and terminal outlines consistent.
  Put the VMID net label beside the output terminal in desktop/mobile drawings
  and exports; the separate voltage information box does not replace that label.
- Component symbols retain their role colors: green for known, red for calculated,
  yellow for missing data. Do not extend symbol color along arbitrary wire runs.
- Use European (IEC rectangular) resistor symbols for miniPCB calculator drawings,
  including divider parts and the load. Keep an open load visible as a faint,
  unfilled resistor with its Open label; it remains electrically absent.
- In the full schematic, use 20 px symbol leads before changing to net color. This is the calculator's
  drawing convention, not a physical lead-length specification. Resistor bodies
  are 52 px tall; keep both leads equal and the rectangular body at its normal size.
- Center full-view resistor symbols within their allocated rows. Grow the drawing for
  series, parallel and mixed networks; keep all resistor symbols vertical.
- Draw connection dots at real three-way and four-way junctions. Do not add dots
  at ordinary bends or at unconnected crossings.
- Check supply, ground, load resistor and current-source boundaries as well as
  divider resistors. Check both a single part and nested series/parallel networks.

## Interaction and information

- Keep Value, Tolerance and Package directly editable on the diagram, populated
  and easy to use. Do not restore the whole-circuit Options dialog. Keep unique
  search limits and automatic-value controls in compact, collapsed sections;
  show search and automatic controls only when applicable. The experimental
  Data & comparisons interface is excluded, not an optional disclosure.
  Retain the backing source fields required by direct editors and the solver,
  with their container hidden and inert; do not expose it during validation.
  A part's focused Options editor may still expose its catalog-specific settings.
- Put Known/Unknown color keys inside the circuit frame so circuit-image exports
  retain them. Keep the four operating-point blocks without a section heading.
- Offer Find Design Solutions only for catalog-combination searches and the
  forward VMID mode with a multi-part network. Calculated inverse quantities
  update directly from their known inputs without an unrelated search action.
- Preserve the active source controls and their labels when reorganizing direct
  SVG editors; these supply input state and metadata. Remove obsolete dialog
  handlers and styling when removing their entry point.
- On phones, default to a fitted compact circuit overview and readable settings
  cards. Equivalent-arm symbols may be smaller; retain every physical part's
  editable value, tolerance and package. Collapse secondary analysis and BOM data.
  Use at least 44 px touch targets and 16 px native input text; ordinary input
  configuration must not require sideways scrolling or a right click.
- Offer Desktop view on phones to restore the complete schematic and information.
  Layout/disclosure changes preserve circuit state, selected solutions, build
  identity and clean leave protection. Keep touch construction menus accessible.
- Resistance value editors use a multiplier dropdown (µΩ, mΩ, Ω, kΩ, MΩ, GΩ).
  Continue accepting typed unit suffixes, synchronize the selected multiplier,
  and compute nearest suggestions in ohms without applying a multiplier twice.
- Let known/calculated roles determine editability in every mode. Preserve the
  selected mode and other physical parts when editing one resistor.
- Do not restore Find RL/IL as a calculator mode. Resistor and current loads,
  including their tolerances, remain known inputs in the other modes.
- Keep each parts-list reference and its entire edit target within its row.
  Use explicit row-local rectangles rather than text decoration that can extend
  beyond the row. Increase table fonts on large screens, stack complete part
  numbers on phones and avoid repeating exact-match specifications. Descriptions
  include the physical part's TCR in ppm/C (assigned catalog TCR takes precedence
  over the manual operating-condition default). Preserve full BOM/export data.
- Keep Pstress and Vstress compact and tied to each actual part's ratings. Label
  nominal versus worst-case results accurately. Format stress as nonnegative
  percentages with two decimals; missing ratings are unassessed, not zero.
- A footprint alone does not identify a manufacturer or power mode. Unassigned
  parts, including fresh/reset 0805 defaults and inserted siblings, use the lowest
  documented package references across supported families. A package-only edit
  must not assign an MPN. Preserve an explicitly assigned family/mode when its
  footprint changes, and honor explicit manual power/voltage overrides.
  Route assignments through `storeCatalogAssignment` to replace the package
  reference flag and stored power allowance together, including search Apply
  and automatic values; a stale reference flag can overwrite a real rating.
- Compute each physical part's P = I²R = V²/R. Pstress and Vstress divide that
  part's power and absolute voltage by independent design limits; never replace
  continuous working voltage with sqrt(Pallowed*R) or the insulation-test rating.
  Keep raw P70/base ratings separate from ambient derating, apply shared design
  percentages once, and verify fresh -> other package -> original package gives
  identical stresses when the part specification is unchanged. Interior
  matched-load power maxima and conservative network bounds are documented by
  the stress functions; zero load at zero allowance must not produce NaN.
- Carry configured initial, thermal, radiation/aging and load uncertainty through
  every mode. Distinguish inverse trip-voltage ranges from allowable source
  tolerance budgets; avoid counting derived uncertainty twice.
- Use the real repository `logo.png`; do not invent or redraw miniPCB branding.
- Export the currently displayed circuit or selected preview. Preserve the title
  and real logo, embed assets for offline use, and remove editing/action controls.
  Keep framed-circuit downloads distinct from full-workspace downloads.
- Accept embedded data images in self-contained SVGs; verify their original asset
  bytes when testing branding.
- Verify visual changes on desktop and phone, in series/parallel/mixed circuits,
  and in exported images. Check text fit, symbol size, lead boundaries, node dots
  and live updates after a value, tolerance or package change.

## Analysis traceability

- Put the published UTC build date/time and short Git commit ID directly beneath
  the miniPCB logo on calculator diagrams. Link the stamp to the exact public
  GitHub commit so an exported analysis can be traced to its calculator source.
- Use the shared `calculators/build.json` metadata generated by GitHub Pages from
  `site.time` and `site.github.build_revision`. Keep this build identity fixed
  while inputs, selected solutions, filters or viewport size change. Do not use
  the current clock or the repository's latest commit as the published revision.
- Keep the analysis date/time separate from the build date/time. Local previews
  or unavailable build metadata must be labeled as unpublished; never invent a
  commit ID or present an analysis timestamp as a published build timestamp.
- Preserve the stamp and full commit metadata in full-workspace and framed SVG
  downloads, and keep the date/time and short commit visible in PNG, JPEG and BMP
  exports. Leave enough header space for the logo, stamp and editable circuit
  title without overlap, including long titles and large resistor networks.
- Verify metadata loading, unchanged build identity after edits, local fallback,
  desktop/phone fit and exported stamp content when changing this feature.
