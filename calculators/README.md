# Moving the Voltage Divider Calculator to another website

The calculator is a static, browser-based application. A functional copy needs
the calculator HTML, five JavaScript modules, the local resistor catalogs and a
few image assets. There is no application server, database, package installation,
API key or third-party JavaScript CDN dependency. GitLab Pages and ordinary
static web hosting can serve it.

This guide assumes you want an independent copy with the current calculations,
catalog searches, schematic editors, BOM and downloads. Keep the directory
layout below; it works at a domain root or inside a project subdirectory.

## Files to copy

Paths in this table are relative to the repository root.

| File | Function and migration notes |
| --- | --- |
| [calculators/voltage_divider.html](voltage_divider.html) | Application entry point. Contains its own CSS and most calculation, network construction, search, chart, editor, BOM and LTspice/Markdown export code. Copy the entire file, including the hidden backing form controls. |
| [js/resistor-parts.js](../js/resistor-parts.js) | Loads and validates the catalog manifest and family files; generates, decodes and suggests supported part numbers and preferred values; applies catalog ratings and ambient power derating. |
| [js/resistor-environment.js](../js/resistor-environment.js) | Initial/thermal/radiation/aging resistance intervals, environmental defaults and family-specific drift models. This is executable calculation logic, separate from the ordering catalogs. |
| [js/divider-current-load.js](../js/divider-current-load.js) | Signed current-load analysis, inverse calculations and tolerance/stress bounds, including Find VTOP trip-voltage ranges. |
| [js/circuit-image-export.js](../js/circuit-image-export.js) | Framed SVG, PNG, JPEG and BMP encoding, raster size limits and download filenames. |
| [js/divider-memory.js](../js/divider-memory.js) | Collapsible calculation history, editable names, changes from the original state, grouped autosaving, local browser storage, duplicate suppression and recall controls. The HTML adapter describes and serializes full circuit inputs and recalculates recalled designs. |
| [parts/index.json](../parts/index.json) | Catalog manifest and preferred-value series. Names both family JSON files to fetch. |
| [parts/resistors/vishay-tnpw-e3.json](../parts/resistors/vishay-tnpw-e3.json) | Supported Vishay TNPW e3 ordering rules, packages, tolerances, TCR options, operating modes, electrical limits and dated source evidence. |
| [parts/resistors/vishay-eh-m55342.json](../parts/resistors/vishay-eh-m55342.json) | Corresponding Vishay E/H M55342/D55342 rules and limits. This is a specific manufacturer's supported subset of the specification family. |
| [logo.png](../logo.png) | The real miniPCB logo, displayed in the format picker and fetched into the circuit. Its original bytes are embedded in generated images. |
| [images/voltage_divider.svg](../images/voltage_divider.svg) | Static fallback drawing and initial SVG download target. It is not the interactive calculator or a saved user design. |
| [favicon.png](../favicon.png) | Existing miniPCB browser icon. Its current root-relative link needs adjustment on a project-subdirectory site. |
| [calculators/build.json](build.json) | Published build identity used beneath the logo and in exports. **Generate this for the destination host**; the source file is a GitHub Pages/Jekyll template, not plain JSON. See below. |

Recommended support files, which are not required by the running application:

| File or directory | Purpose |
| --- | --- |
| [parts/schema.json](../parts/schema.json) | JSON Schema for maintaining the catalog data. Catalog loading performs its own JavaScript validation; it does not fetch this schema. |
| [parts/README.md](../parts/README.md) | Catalog scope, numbering conventions, sources and data-maintenance instructions. Its catalog-engine discussion is separate from the calculator's environmental interval model. |
| [md/voltage_divider_sch.md](../md/voltage_divider_sch.md) | Detailed calculation, interaction and export documentation. A hand-authored guide, rather than a live session export. |
| [calculators/tests/](tests/) | Browser regression pages. Keep these in a development copy; they need not be published with the production calculator. |
| [AGENTS.md](../AGENTS.md), [calculators/AGENTS.md](AGENTS.md) and the root agent logs | Maintenance conventions, calculator physics/UI notes and change history. Not runtime dependencies. |

You do not need the rest of the board catalog, storefront, proxy, datasheets
directory, `styles.css`, `js/minipcb.js` or other site pages to run this tool.
`tools.html` is only a breadcrumb destination; remove or repoint that link.
The existing `ltspice/voltage_divider.asc` is a static example: live LTspice
downloads are generated from the displayed circuit and do not read that file.
Do not copy the repository's `CNAME` unless you intend to configure that same
custom domain.

## Preserve this published layout

```text
site-root/
├── index.html                         # New landing page or relative redirect
├── logo.png
├── favicon.png
├── calculators/
│   ├── voltage_divider.html
│   └── build.json                     # Generated plain JSON
├── js/
│   ├── resistor-parts.js
│   ├── resistor-environment.js
│   ├── divider-current-load.js
│   ├── circuit-image-export.js
│   └── divider-memory.js
├── parts/
│   ├── index.json
│   ├── schema.json                    # Recommended; not fetched at runtime
│   └── resistors/
│       ├── vishay-tnpw-e3.json
│       └── vishay-eh-m55342.json
└── images/
    └── voltage_divider.svg
```

Open `calculators/voltage_divider.html`. A root `index.html` can link or redirect
to it. Simply renaming/copying the calculator to the root as `index.html` breaks
its relative asset paths unless you also update them.

The page loads its scripts from `../js/`, its logo from `../logo.png`, its
fallback image from `../images/`, and build metadata from `build.json` beside the
page. `resistor-parts.js` locates `../parts/` **relative to its own script URL**,
then loads `index.json` and the manifest's family paths. Moving only the page
or only that script requires corresponding path changes. Keep filename case
exact on Linux hosts. Keep the five classic script tags in their existing order,
before the main inline script; do not add `async` or change them to modules.

## Hosting and browser considerations

- Serve the files over HTTP for local development and HTTPS for publishing.
  Opening the HTML with `file://` prevents reliable catalog/logo fetching. For
  example, run `python -m http.server 8000` from `site-root`, then visit
  `http://localhost:8000/calculators/voltage_divider.html`.
- Keep assets on the same origin. A missing catalog disables real-part searches
  and suggestions while manual analysis remains available; a missing required
  JavaScript module can stop initialization. Return the actual JSON/JS files,
  not an HTML catch-all or sign-in page, for asset requests.
- The app uses modern JavaScript, interactive SVG with HTML `foreignObject`
  editors, native dialogs, Blob URLs, canvas and browser downloads. Test with
  current desktop and phone browsers. Clipboard copying works best in a secure
  context and has a manual-copy fallback.
- A host's restrictive Content Security Policy must accommodate the existing
  inline script/styles and editor styling, same-origin fetches and assets,
  `data:` image embedding and `blob:` image/download URLs. Embedding in a
  sandboxed iframe also needs permissions for scripts, same-origin access and
  downloads. A normal top-level static page avoids those iframe restrictions.
- Computation and file generation stay in the browser. Manufacturer/source
  URLs are reference links, not runtime catalog APIs. There is no service worker
  or installed offline application; a local HTTP server can operate without
  internet access once the copied files are available.
- Calculation memory uses local storage (`minipcb-divider-memory-v1`) for up to
  50 valid calculations, including the retained original, and its autosave
  preference. It groups completed edits after a one-second pause. Right-click
  Memory or an entry for Save now, rename, autosave, delete and clear; Shift+F10
  and touch long press open the same menu.
  F2 renames a focused entry. Names and bullet changes from a fixed Original state
  describe full independent snapshots: editing a recalled state saves a new one.
  Existing history uses its oldest available state as the original reference;
  the version-2 storage envelope reads old entries without changing their
  version-1 circuit snapshots. Clearing history resets the reference.
  The desktop pane collapses horizontally into a slim rail. Recalling rebuilds
  inputs and recalculates; a search snapshot retains only its selected design,
  not the full result pool. The desktop/mobile view preference uses
  `minipcb-divider-view`. Storage belongs to this browser profile and website
  origin: moving to a different domain does not transfer existing memory.
  Uncommitted editor drafts are not saved; the leave warning remains intentional.
- Publish matching HTML, scripts, catalog data and metadata together. Avoid
  indefinitely caching unversioned files; `build.json` requests revalidation
  with `cache: "no-cache"`. Exported files are snapshots and need a new download
  after circuit edits.

## Paths, source links and build traceability

Before publishing a relocated copy, review these items in
`calculators/voltage_divider.html`:

1. Change `href="/favicon.png"` to `href="../favicon.png"`. The original leading
   slash bypasses a project prefix such as `/my-calculator/`.
2. Remove or repoint the `../tools.html` breadcrumb.
3. Replace occurrences of
   `https://www.minipcb.com/calculators/voltage_divider.html` with the destination
   calculator URL. They appear in report metadata, LTspice/Markdown exports and
   comparison CSV source attribution. Leave manufacturer evidence URLs intact.
4. For a GitLab fork, set `calculatorRepository` to the destination repository
   URL and change both `${calculatorRepository}/commit/` constructions to
   `${calculatorRepository}/-/commit/`. Update the stamp's `GitHub commit`
   accessible label to `GitLab commit` as well. Changing only the repository
   constant does not fix GitLab's commit URL syntax.

The source `calculators/build.json` begins with Jekyll front matter and contains
`{{ site.time }}` / `{{ site.github.build_revision }}` expressions. Plain static
hosting does not expand those. Write an actual JSON object containing `builtAt`
(an ISO 8601 build date/time) and `commit` (the full 40-hex-character revision
of the source being published). The loader currently requires that commit format.

Generate the timestamp once during packaging, and use the checked-out commit,
not a latest-commit lookup or a browser clock. Do not substitute the commit's
authored date for the build date. The separate analysis timestamp changes with
calculations; the build identity must stay fixed. Invalid or absent metadata
produces an **unpublished source** stamp without disabling the calculator.

A changed GitLab copy should link to its own exact revision. An unchanged mirror
can retain upstream provenance only if its metadata and commit link identify the
actual upstream source copied. Do not mix a GitLab SHA with a GitHub commit URL.
The example below generates the fork's metadata and adjusts its links together.

## GitLab Pages example

Copy the listed source files into a new GitLab repository using their original
paths. Put the following in that repository's `.gitlab-ci.yml`. It packages only
the needed files, adapts the published HTML, adds a root redirect, and replaces
the Jekyll metadata template. It does not alter the source checkout.

This example uses current GitLab Pages syntax (GitLab 17.10 or later) and a Linux
container runner. GitLab Pages supports plain static HTML; a generator is not
required. The `pages.publish` directory is collected as a Pages artifact, and it
must contain a nonempty root `index.html`.
([Pages overview](https://docs.gitlab.com/user/project/pages/),
[CI syntax](https://docs.gitlab.com/ci/yaml/#pagespublish))

```yaml
deploy-divider:
  image: python:3.13-alpine
  stage: deploy
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
  script:
    - |
      python - <<'PY'
      import json, os, re, shutil
      from datetime import datetime, timezone
      from pathlib import Path

      output = Path("public")
      files = [
          "calculators/voltage_divider.html",
          "js/resistor-parts.js", "js/resistor-environment.js",
          "js/divider-current-load.js", "js/circuit-image-export.js",
          "js/divider-memory.js",
          "parts/index.json", "parts/schema.json",
          "parts/resistors/vishay-tnpw-e3.json",
          "parts/resistors/vishay-eh-m55342.json",
          "logo.png", "favicon.png", "images/voltage_divider.svg",
      ]
      for name in files:
          target = output / name
          target.parent.mkdir(parents=True, exist_ok=True)
          shutil.copy2(name, target)

      repository = os.environ["CI_PROJECT_URL"].rstrip("/")
      calculator_url = os.environ.get("CALCULATOR_PUBLIC_URL") or (
          os.environ["CI_PAGES_URL"].rstrip("/") + "/calculators/voltage_divider.html"
      )
      page = output / "calculators/voltage_divider.html"
      source = page.read_text(encoding="utf-8")
      source = source.replace('href="/favicon.png"', 'href="../favicon.png"')
      source = source.replace(
          '<a href="../tools.html">Tools</a><span aria-hidden="true">/</span>', ""
      )
      source = source.replace(
          "https://www.minipcb.com/calculators/voltage_divider.html",
          calculator_url,
      )
      source = source.replace(
          'const calculatorRepository = "https://github.com/miniPCB/minipcb.github.io";',
          "const calculatorRepository = " + json.dumps(repository) + ";",
      )
      source = source.replace('${calculatorRepository}/commit/', '${calculatorRepository}/-/commit/')
      source = source.replace('; GitHub commit ${build.commit}', '; GitLab commit ${build.commit}')
      page.write_text(source, encoding="utf-8")

      commit = os.environ["CI_COMMIT_SHA"]
      assert re.fullmatch(r"[a-fA-F0-9]{40}", commit), "Expected a full source revision"
      metadata = {"builtAt": datetime.now(timezone.utc).isoformat(), "commit": commit}
      (output / "calculators/build.json").write_text(json.dumps(metadata) + "\n", encoding="utf-8")
      (output / "index.html").write_text(
          '<!doctype html><html lang="en"><meta charset="utf-8">'
          '<meta name="viewport" content="width=device-width, initial-scale=1">'
          '<title>Voltage Divider Calculator</title>'
          '<meta http-equiv="refresh" content="0;url=calculators/voltage_divider.html">'
          '<a href="calculators/voltage_divider.html">Open the voltage divider calculator</a></html>\n',
          encoding="utf-8",
      )
      PY
  pages:
    publish: public
```

`CI_PROJECT_URL`, `CI_COMMIT_SHA` and `CI_PAGES_URL` come from GitLab. If a custom
domain should appear in downloaded reports, set your own `CALCULATOR_PUBLIC_URL`
CI/CD variable to the full public calculator URL. Use the actual Pages URL shown
by GitLab rather than assuming a particular domain/project-prefix scheme.
([GitLab variable reference](https://docs.gitlab.com/ci/variables/predefined_variables/))

This recipe assumes the source paths and original miniPCB URL strings above have
not already been reorganized. Review its replacements if you customize the source.
For an existing website, merge the copy/metadata steps into its build and retain
its landing page instead of overwriting `public/index.html`. The example is
intended for a dedicated calculator repository.

## Verify the moved copy

Serve the packaged output itself: `python -m http.server 8000 --directory public`.
For a project-prefix check, also serve its parent directory and open
`/public/calculators/voltage_divider.html`; this catches accidental root-relative
paths before deployment.

1. Check the browser Network/Console panels. All five scripts, the catalog
   manifest and both family files, logo, fallback SVG, favicon and generated
   `build.json` should load without missing files or JSON parsing errors.
2. Change value, tolerance and package; add series/parallel parts; check Find
   VMID, Find VTOP with a signed current load, inverse resistance modes and a
   real-part search. Confirm both TNPW and M55342 are available under compatible
   package/tolerance/TCR settings. Validate your known reference circuit too.
3. Check Pstress/Vstress updates and operating-condition bounds. Confirm the
   build stamp opens the exact fork commit, stays fixed after edits, and the
   separate analysis time updates.
4. Copy the BOM; download full SVG, framed SVG/PNG/JPEG/BMP, LTspice and Markdown.
   Check title, logo, circuit, physical part data, source URL and build identity.
   Open exported images without relying on the original miniPCB website.
5. Test a phone-width screen, desktop view, direct input editing and the parts
   list. Confirm the leave/reload warning and clipboard fallback remain usable.
   Save and recall a calculation, reload the page and confirm browser memory is
   retained, including custom names. Change a recalled design and confirm the
   previous snapshot remains intact and the bullets compare against the original.
   If storage is blocked, memory must report that it lasts for the visit.

For automated browser coverage, copy `calculators/tests/` into the development
tree and open its HTML pages over the same local server. Each reports JSON with
`status: "PASS"` or a failure list. Useful starting points are
`voltage_divider.html`, `resistor_pairs.html`, `package_tolerance_search.html`,
`current_load_modes.html`, `package_rating_consistency.html`,
`package_stress_refresh.html`, `mobile_workspace.html`, `parts_table_layout.html`,
`schematic_bom.html`, `frame_export.html`, `circuit_downloads.html`,
`calculator_stamp.html`, `calculator_memory.html` and `calculator_memory_names.html`.
These filenames refer to test pages inside `calculators/tests/`, not the
application entry point.

Some tests assert the original miniPCB/GitHub URLs and branding; adapt those
expectations when testing a fork. `resistor_parts.html` also tests
`part_number_radar.html`, which is outside the minimal copy; include that tool
and its assets or separate its integration checks. Run resize/animation tests in
real browser time so the layout and transition handlers can settle.

## Preserve the engineering meaning

Catalog files contain supported ordering subsets and dated evidence, not supplier
stock or a guarantee that every possible manufacturer part is represented. Keep
their sources and revision fields. Changes to catalog rules, environmental models
or stress limits need calculation regression checks as well as a successful page
load. Current radiation and aging defaults are each 0.1% estimated resistance
allowances, not orbit/dose/lifetime qualification. The environmental module and
calculator documentation describe the interval assumptions.

The real-part search can be bounded by its assignment/result budget; copying the
tool must not turn a bounded search into a claim of exhaustive coverage. LTspice
exports are nominal `.op` circuits with tolerance/rating annotations and measured
reports, not implementations of the calculator's worst-case tolerance sweeps.
Keep those distinctions, independent power/voltage limits and per-physical-part
ratings when integrating or simplifying the interface.
