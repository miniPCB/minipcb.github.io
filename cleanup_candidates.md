# Rough tool cleanup candidates

The four rough tools below have been removed from `tools.html`. Their pages and
supporting files remain in the repository. This is a review list, not a deletion
manifest.

## Pages to consider deleting or archiving

| Tool | Candidate file | Related files and checks |
| --- | --- | --- |
| Engineering Analyzer | [engineering_analyzer.html](engineering_analyzer.html) | Reads/writes analysis reports and setup data under `json/fmea/`. Review those artifacts separately before changing them. |
| Engineering Analyzer specification | [engineering_analyzer_spec.html](engineering_analyzer_spec.html) | Specification for the analyzer; review alongside its implementation. It also has its own entry in `site_index.js`. |
| Catalog Reader | [minipcb_2026.html](minipcb_2026.html) | Uses `schematics-data.js`, `md/index.json`, board markdown/JSON/images, and saved FMEA reports. Those assets are not automatically cleanup candidates. |
| Catalog Browser | [catalog_browser.html](catalog_browser.html) | Uses the shared `site_index.js` catalog. |
| Board Finder | [board_finder.html](board_finder.html) | Contains its own interface and calls the shared `/api/part-request` service. |

## References to address before deleting pages

- [index.html](index.html): introductory tool descriptions, the "Pages and How To
  Use Them" list, and workflow text still mention the four tools. Its generated
  catalog also reads `site_index.js`.
- [site_index.js](site_index.js): entries remain for all five candidate HTML
  files. After any deletion, update the index or regenerate it with
  [scripts/generate_site_index.py](scripts/generate_site_index.py), reviewing the
  resulting diff. Regenerating while a page remains will include it again.
- `engineering_analyzer_spec.html` mentions `engineering_analyzer.html`; remove
  or revise that reference if the specification is retained.
- Check for newly added references and decide how existing public URLs should
  behave before removing their targets.

## Shared files and data to keep out of automatic cleanup

- [site_index.js](site_index.js) and [schematics-data.js](schematics-data.js)
  support the homepage; removing a tool does not retire these indexes or their
  generators.
- `md/index.json`, board markdown, board JSON, and images are engineering
  artifacts, not disposable viewer assets.
- `json/fmea/` contains saved reports and setup files. Review their content and
  provenance independently of the analyzer and reader pages.
- [proxy-vercel/api/part-request.js](proxy-vercel/api/part-request.js) is also used
  by [part_number_radar.html](part_number_radar.html) and
  [part_number_browser.html](part_number_browser.html). Keep that service and its
  shared utilities when retiring Board Finder.

The current change only removes the four Tools cards and updates the remaining
page descriptions. It does not remove homepage/index references or delete any
candidate files.
