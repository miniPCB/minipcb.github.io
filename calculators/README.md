# Moving the calculators to another website

The Voltage Divider and Ohm’s Law calculators run in the browser. Serve their HTML, JavaScript, and local assets on any static web host. They need no application server, database, API key, or JavaScript CDN. You can publish either calculator on its own or both together.

## Files to copy

Paths are relative to the repository root. Copy the shared files once, then add the files for each calculator you want to publish.

| Calculator | Entry point | Additional files |
| --- | --- | --- |
| Voltage Divider | [calculators/voltage_divider.html](voltage_divider.html) | [js/resistor-environment.js](../js/resistor-environment.js), [js/divider-current-load.js](../js/divider-current-load.js), and [images/voltage_divider.svg](../images/voltage_divider.svg). The page includes its CSS, main application script, design search, BOM, and export logic. Keep the entire HTML, including its hidden backing controls. |
| Ohm’s Law | [calculators/ohms_law.html](ohms_law.html) | [calculators/ohms_law.css](ohms_law.css) and [js/ohms-law.js](../js/ohms-law.js). The script handles source and resistor editing, series and parallel networks, tolerance ranges, stress, and circuit downloads. |

| Shared file | Purpose |
| --- | --- |
| [js/calculator-memory.js](../js/calculator-memory.js) | Memory drawer, autosave, and saved calculation recall. Use the version from the same checkout as the pages. |
| [js/circuit-image-export.js](../js/circuit-image-export.js) | Framed SVG, PNG, JPEG, and BMP exports. |
| [js/resistor-parts.js](../js/resistor-parts.js) | Local catalog loader. The Voltage Divider uses it for part selection and ratings. Ohm’s Law uses it for footprint power and voltage references. |
| [parts/index.json](../parts/index.json) | Catalog manifest and preferred-value series. Copy every family file listed in `families[].file`, relative to `parts/`. |
| [parts/resistors/vishay-tnpw-e3.json](../parts/resistors/vishay-tnpw-e3.json) and [parts/resistors/vishay-eh-m55342.json](../parts/resistors/vishay-eh-m55342.json) | The two families in the current manifest. Retain their source and revision fields. |
| [logo.png](../logo.png) | Logo used in the circuit, export dialog, and generated images. A missing logo can prevent image exports. |
| [favicon.png](../favicon.png) | Browser icon. Copy it with the existing icon links, or change those links to your site’s icon. |
| [calculators/build.json](build.json) | Optional build attribution. Generate plain JSON at this path for a generic static host. The repository file is a GitHub Pages/Jekyll template. |

For catalog maintenance, keep [parts/schema.json](../parts/schema.json) and [parts/README.md](../parts/README.md). The browser loader validates the data itself. The [divider calculation notes](../md/voltage_divider_sch.md), [static LTspice example](../ltspice/voltage_divider.asc), [calculator editing conventions](AGENTS.md), and [browser tests](tests/) can stay in the development checkout.

[Part Number Radar](../part_number_radar.html) can use the same resistor catalog at the site root and is a fixture for the catalog integration test. Its part request and availability features use a separate service. If you are also migrating that tool, see the [proxy deployment guide](../proxy-vercel/README.md).

## Publish on a static host

1. Keep the copied files in sibling directories under your chosen publishing root. This works at a domain root or under a project prefix.

   ```text
   site-root/
   ├── index.html                 # Your landing page, if needed
   ├── logo.png
   ├── favicon.png
   ├── calculators/
   │   ├── voltage_divider.html   # If publishing the Voltage Divider
   │   ├── ohms_law.html          # If publishing Ohm’s Law
   │   ├── ohms_law.css           # Ohm’s Law stylesheet
   │   └── build.json             # Optional generated metadata
   ├── js/                        # Shared modules and selected tool scripts
   ├── parts/                     # Manifest and its family files
   └── images/                    # Voltage Divider fallback schematic
   ```

2. Link to each selected page from your site navigation and repoint the `../tools.html` breadcrumbs. For a project prefix, change the Voltage Divider’s `/favicon.png` to `../favicon.png`. Ohm’s Law already uses a relative icon link. Configure the destination domain through your host. The repository’s [CNAME](../CNAME) belongs to miniPCB.
3. Keep the page-relative paths and exact filename case. The calculators load scripts from `../js/` and the logo from `../logo.png`. Ohm’s Law loads its stylesheet beside its page. The Voltage Divider loads its fallback from `../images/`. The catalog loader resolves `../parts/` relative to its own script URL. Preserve script order and loading attributes. The Voltage Divider’s scripts run before its inline app, and Ohm’s Law uses ordered `defer` scripts.
4. Preview over HTTP, then publish over HTTPS. From the publishing root, run `python -m http.server 8000` and visit `http://localhost:8000/calculators/voltage_divider.html` or `http://localhost:8000/calculators/ohms_law.html`. From one directory above the publishing root, test again with the publishing directory in the URL to catch accidental root-relative references.

Serve JavaScript, catalog JSON, and images from the same origin and return the actual files for those requests. A missing catalog can disable part search and leave some footprint ratings unavailable. Publish pages, scripts, styles, and catalogs from the same checkout. On updates, revalidate unversioned assets or update their query-string versions. A `?v=…` suffix is part of the URL only.

Use a current browser that supports interactive SVG, `foreignObject` editors, native dialogs, canvas, and browser downloads. If the destination uses Content Security Policy, account for the calculators’ inline scripts and styles, same-origin fetches, and `data:` and `blob:` URLs for images and downloads. A sandboxed iframe also needs the permissions those features require. Clipboard copying has a manual fallback for browsers that restrict clipboard access.

Calculation Memory is local to the browser profile and site origin. The Voltage Divider uses `minipcb-divider-memory-v1` and Ohm’s Law uses `minipcb-ohms-law-memory-v1`. A copy on a different origin starts with separate history. A copy at a different path on the same origin uses the same history key for that tool. Download any reports you need to retain before moving sites.

## Build and source attribution

Both calculators read `calculators/build.json` from beside their HTML. For a published build, write plain JSON with these fields.

| Field | Value |
| --- | --- |
| `builtAt` | ISO 8601 timestamp generated once when the site is packaged, with its timezone. |
| `commit` | Full 40-character hexadecimal Git revision of the code being published. |

The build stamp stays fixed while the circuit changes. The Voltage Divider also shows a separate analysis timestamp. The calculators show **Unpublished source** in local previews without valid build metadata. A plain server will not expand the checked-in [Jekyll template](build.json).

For a fork, update the corresponding source links as well as the metadata.

- In [voltage_divider.html](voltage_divider.html), replace the original public calculator URL used in reports and CSV exports. Set `calculatorRepository` to the repository being published and update its commit URL pattern and accessible label for the destination Git host.
- In [js/ohms-law.js](../js/ohms-law.js), update the commit URL in the schematic stamp and the one in the Markdown report.
- Keep manufacturer evidence links intact. If the build points to an upstream revision, ensure the timestamp, revision, and commit link all describe the build being served.

## GitLab Pages example

This job packages either calculator or both. It generates a small landing page, rewrites the published copies’ navigation and attribution, and versions their script and stylesheet URLs by content. Use it in a dedicated calculator repository or integrate the copy steps into your existing site build. GitLab Pages serves the artifact from `public/`, which needs a root `index.html`. [GitLab Pages guide](https://docs.gitlab.com/user/project/pages/) · [GitLab CI publish syntax](https://docs.gitlab.com/ci/yaml/#pagespublish)

Put this in `.gitlab-ci.yml`. Both calculators are published by default. Set the optional `CALCULATORS` variable to `voltage_divider` or `ohms_law` to publish only one.

```yaml
deploy-calculators:
  image: python:3.13-alpine
  stage: deploy
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
  script:
    - |
      python - <<'PY'
      import hashlib
      import json
      import os
      import re
      import shutil
      from datetime import datetime, timezone
      from html import escape
      from pathlib import Path

      tools = {
          "voltage_divider": (
              "Voltage Divider Calculator",
              ["js/resistor-environment.js", "js/divider-current-load.js",
               "images/voltage_divider.svg"],
          ),
          "ohms_law": (
              "Ohm’s Law Calculator",
              ["calculators/ohms_law.css", "js/ohms-law.js"],
          ),
      }
      selected = [name.strip() for name in os.getenv("CALCULATORS", ",".join(tools)).split(",")]
      if any(name not in tools for name in selected):
          raise SystemExit("CALCULATORS must contain voltage_divider, ohms_law, or both.")
      selected = list(dict.fromkeys(selected))

      output = Path("public")
      manifest = Path("parts/index.json")
      catalog = json.loads(manifest.read_text(encoding="utf-8"))
      files = [
          "logo.png", "favicon.png", "js/calculator-memory.js",
          "js/circuit-image-export.js", "js/resistor-parts.js", manifest,
          *(manifest.parent / family["file"] for family in catalog["families"]),
      ]
      for name in selected:
          files.extend([f"calculators/{name}.html", *tools[name][1]])

      for path in files:
          target = output / path
          target.parent.mkdir(parents=True, exist_ok=True)
          shutil.copy2(path, target)

      repository = os.environ["CI_PROJECT_URL"].rstrip("/")
      public_base = (os.getenv("CALCULATORS_PUBLIC_BASE_URL") or os.environ["CI_PAGES_URL"]).rstrip("/")
      upstream_repository = "https://github.com/miniPCB/minipcb.github.io"
      commit_path = "/-/commit/"
      if "ohms_law" in selected:
          script = output / "js/ohms-law.js"
          source = script.read_text(encoding="utf-8").replace(
              upstream_repository + "/commit/", repository + commit_path
          )
          script.write_text(source, encoding="utf-8")

      asset_url = re.compile(r'\b(src|href)="(\.\./js/[^"?]+\.js|ohms_law\.css)(?:\?[^"]*)?"')
      links = []
      for name in selected:
          label = tools[name][0]
          path = f"calculators/{name}.html"
          page = output / path
          source = page.read_text(encoding="utf-8")
          source = source.replace('href="/favicon.png"', 'href="../favicon.png"')
          source = source.replace('href="../tools.html"', 'href="../index.html"')
          if name == "voltage_divider":
              url = os.getenv("CALCULATOR_PUBLIC_URL") or f"{public_base}/{path}"
              source = source.replace("https://www.minipcb.com/calculators/voltage_divider.html", url)
              source = source.replace(json.dumps(upstream_repository), json.dumps(repository))
              source = source.replace("${calculatorRepository}/commit/", "${calculatorRepository}" + commit_path)
              source = source.replace("; GitHub commit", "; GitLab commit")

          def version_asset(match):
              attribute, relative_url = match.groups()
              digest = hashlib.sha256((page.parent / relative_url).read_bytes()).hexdigest()[:12]
              return f'{attribute}="{relative_url}?v={digest}"'

          page.write_text(asset_url.sub(version_asset, source), encoding="utf-8")
          links.append(f'<li><a href="{path}">{escape(label)}</a></li>')

      commit = os.environ["CI_COMMIT_SHA"]
      if not re.fullmatch(r"[a-fA-F0-9]{40}", commit):
          raise SystemExit("Expected a full source revision")
      metadata = {"builtAt": datetime.now(timezone.utc).isoformat(), "commit": commit}
      (output / "calculators/build.json").write_text(json.dumps(metadata) + "\n", encoding="utf-8")
      (output / "index.html").write_text(
          '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
          '<meta name="viewport" content="width=device-width, initial-scale=1">'
          '<title>Calculators</title></head><body><main><h1>Calculators</h1><ul>\n'
          + "\n".join(links) + '\n</ul></main></body></html>\n',
          encoding="utf-8",
      )
      PY
  pages:
    publish: public
```

The job uses GitLab’s `CI_PROJECT_URL`, `CI_COMMIT_SHA`, and `CI_PAGES_URL`. To use a custom domain in attribution, set `CALCULATORS_PUBLIC_BASE_URL` to the published site base URL, including any project prefix. `CALCULATOR_PUBLIC_URL` can override the full Voltage Divider URL. The replacements assume the original miniPCB source strings, so review them if you have already customized the code. [GitLab predefined variables](https://docs.gitlab.com/ci/variables/predefined_variables/)

To add another calculator to the recipe, add a `tools` entry keyed by its HTML filename without `.html`. List its tool-specific styles, scripts, and fetched assets. Include any page-specific URL rewrites and extend the asset matcher if the new page uses other stylesheet paths.

## Verify the moved copy

Serve the prepared output itself with `python -m http.server 8000 --directory public`. If you adapted the example for an existing site, use its own publishing directory.

1. Open each selected calculator from the landing page and confirm that its breadcrumb returns there. Check the browser Network and Console panels for script, stylesheet, catalog, and image failures. If you publish build metadata, verify that the stamp opens the exact deployed revision and stays fixed during edits.
2. **Voltage Divider.** Confirm that equal divider resistors and an open load produce half the input voltage. Check the solve modes, a signed current load, tolerance bounds, real-part search, and the parts list. Verify a selection from each catalog family under compatible settings.
3. **Ohm’s Law.** Confirm that 12 V across 1 kΩ produces 12 mA. Add series and parallel resistors, edit their values, tolerances, and footprints, and check dissipation and stress. Switch to a current source and verify the calculated load voltage and tolerance range.
4. Try the direct editors, Memory recall, and Circuit Characteristics on desktop and at phone width. Reload and confirm the saved circuit can be recalled. Download a framed image, LTspice schematic, and Markdown report from each tool and check the current circuit, units, and attribution. For the Voltage Divider, also verify the full schematic export and parts-list copy.

For browser regression checks, keep [calculators/tests/](tests/) in the development tree and serve it over HTTP. Start with the [divider mode checks](tests/mode_interactions.html), [Ohm’s Law checks](tests/ohms_law.html), [build stamp checks](tests/calculator_stamp.html), [framed export checks](tests/frame_export.html), and [Memory drawer checks](tests/memory_drawer.html). The Ohm’s Law test prints a list of passed checks or a failure. The divider mode and stamp tests report a JSON status.

Some integration checks expect the original site navigation, page markup, or GitHub attribution. The [broader divider suite](tests/voltage_divider.html) fetches [tools.html](../tools.html) and still expects the retired `.live-tag` heading. The [catalog integration test](tests/resistor_parts.html) loads [Part Number Radar](../part_number_radar.html). Copy the fixtures or adapt the assertions for the destination. The test pages can stay out of production.

The catalog gives supported part families with documented limits. Keep power and continuous working voltage as independent limits, and retain the calculation assumptions if you adapt the tools. The Voltage Divider’s part search is bounded by its search budget. The LTspice downloads represent nominal operating points. Use the calculators’ tolerance results for the reported bounds.
