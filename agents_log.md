# Agents Log

Modern revision-block replacement for this repo.  
Human-readable summary + machine-readable source of truth in `agents_log.jsonl`.

## AI Update Protocol (Required)
1. For every change to code/content/config, append one JSON record to `agents_log.jsonl`.
2. Add one summary row to the table below with the same `entry_id`.
3. Do not edit or delete old log records. If needed, append a new record with `change_type: "correction"` or `change_type: "supersede"`.
4. If data is uncertain, keep the entry and set `confidence: "inferred"` with a clear note.
5. Always list changed files and verification performed (or explicitly state not run).
6. Every new JSON record must include `file_edits` with file names and explicit edit statements.

## Record Fields (JSONL)
- `entry_id`: unique id (`YYYYMMDD-HHMMSS-actor-slug`)
- `timestamp`: ISO-8601 with timezone
- `actor`: human name or bot id
- `change_type`: `feature|fix|refactor|process|docs|correction|supersede`
- `status`: `completed|partial|reverted|superseded`
- `summary`: short sentence
- `files`: changed files
- `file_edits`: array of `{ "file": "<path>", "edits": ["statement 1", "statement 2"] }`
- `verification`: tests/checks run (or `"not_run"`)
- `confidence`: `confirmed|inferred`
- `notes`: optional context/tradeoffs

Historical note: entries created before `file_edits` became required may not include it.

## Snapshot
- Repo: `minipcb.github.io`
- Branch: `main`
- Head (best effort at log bootstrap): `232c2f7`
- Primary active surface in recent work: `part_number_radar.html`

## Entries
| Entry ID | Timestamp | Actor | Type | Summary | Files | Verification | Confidence |
|---|---|---|---|---|---|---|---|
| 20260304-181500-codex-reference-db-family-sources | 2026-03-04T18:15:00-06:00 | codex | refactor | Added machine-readable family source registry and family reference-key wiring in radar. | `part_number_radar.html` | manual review | inferred |
| 20260304-184500-codex-diode-initial-implementation | 2026-03-04T18:45:00-06:00 | codex | feature | Implemented initial diode builder/decoder structure before series-level redesign. | `part_number_radar.html` | esprima syntax parse | inferred |
| 20260304-190814-codex-diode-series-hierarchy | 2026-03-04T19:08:14-06:00 | codex | refactor | Refactored diode model to datasheet-series hierarchy (series -> device type -> suffixes), replaced single-PN family model. | `part_number_radar.html` | esprima syntax parse | confirmed |
| 20260304-191305-codex-engineering-log-bootstrap | 2026-03-04T19:13:05-06:00 | codex | process | Bootstrapped engineering log system and bot update rules. | `engineering_log.md`, `engineering_log.jsonl`, `AGENTS.md` | manual review | confirmed |
| 20260304-192210-codex-diode-pill-detail-labels | 2026-03-04T19:22:10-06:00 | codex | docs | Expanded diode pill labels so every selectable option includes explicit meaning/context. | `part_number_radar.html`, `engineering_log.md`, `engineering_log.jsonl` | esprima syntax parse | confirmed |
| 20260304-192802-codex-agents-log-rename-policy | 2026-03-04T19:28:02-06:00 | codex | process | Renamed `engineering_log.*` to `agents_log.*` and required per-file edit statements for new records. | `AGENTS.md`, `agents_log.md`, `agents_log.jsonl` | manual review | confirmed |
| 20260304-194649-codex-diode-datasheet-detail-refresh | 2026-03-04T19:46:49-06:00 | codex | refactor | Redid diode details with datasheet-specific unique selectors per device code and device-aware quality-prefix validation. | `part_number_radar.html`, `agents_log.md`, `agents_log.jsonl` | manual review (node check not run: node missing) | confirmed |
| 20260304-200300-codex-family-current-block-refresh | 2026-03-04T20:03:00-06:00 | codex | docs | Removed `unique selector:` text and refreshed Current Family content for all families with datasheet-derived purpose, strengths, and application context. | `part_number_radar.html`, `agents_log.md`, `agents_log.jsonl` | manual review | confirmed |
| 20260304-203759-codex-clear-filters-empty-state-fix | 2026-03-04T20:37:59-06:00 | codex | fix | Fixed Clear Filters so each family clears to unselected state and clear-button color returns to normal when fully cleared. | `part_number_radar.html`, `agents_log.md`, `agents_log.jsonl` | manual review | confirmed |
| 20260304-210602-codex-m32535-family-addition | 2026-03-04T21:06:02-06:00 | codex | feature | Added M32535 capacitor family with splash routing, dedicated code-builder view, datasheet references, detailed pill mappings, and PN decode support. | `part_number_radar.html`, `agents_log.md`, `agents_log.jsonl` | manual review | confirmed |
| 20260304-211906-codex-m32535-combo-constraint-tightening | 2026-03-04T21:19:06-06:00 | codex | fix | Tightened M32535 combination validation with datasheet-based slash/characteristic voltage constraints plus stricter termination and capacitance checks. | `part_number_radar.html`, `agents_log.md`, `agents_log.jsonl` | manual review (node check not run: node missing) | confirmed |
| 20260304-213946-codex-m32535-waterfall-availability-enforcement | 2026-03-04T21:39:46-06:00 | codex | fix | Enforced M32535 waterfall availability using datasheet cap-code matrices so non-existent slash/voltage/cap combinations are rejected in builder and decoder paths. | `part_number_radar.html`, `agents_log.md`, `agents_log.jsonl` | manual review + esprima parse | confirmed |
| 20260304-220617-codex-wsl-wsc-family-implementation | 2026-03-04T22:06:17-06:00 | codex | feature | Implemented WSL and WSC/WSN resistor families with splash routing, builder/decoder support, datasheet references, and datasheet-detailed pill metadata. | `part_number_radar.html`, `agents_log.md`, `agents_log.jsonl` | datasheet review (`.tmp_wsl.pdf`, `.tmp_wscwsn.pdf`) + esprima parse | confirmed |
| 20260304-221118-codex-pill-wording-tighten | 2026-03-04T22:11:18-06:00 | codex | docs | Shortened WSL/WSC information-pill wording and removed low-value qualifier text from tolerance labels. | `part_number_radar.html`, `agents_log.md`, `agents_log.jsonl` | esprima parse | confirmed |
| 20260304-221612-codex-diode-splash-copy-fix | 2026-03-04T22:16:12-06:00 | codex | docs | Corrected 1N6675-1N6677 splash description to identify it as a Schottky diode family. | `part_number_radar.html`, `agents_log.md`, `agents_log.jsonl` | manual review | confirmed |
| 20260304-222936-codex-sgtpl-transformer-family-addition | 2026-03-04T22:29:36-06:00 | codex | feature | Added SGTPL-28 transformer family with datasheet-backed routing, strict listed-combination builder logic, and decoder support. | `part_number_radar.html`, `agents_log.md`, `agents_log.jsonl` | datasheet review (Vishay doc 34647) + esprima parse | confirmed |
