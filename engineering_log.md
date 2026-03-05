# Engineering Log

Modern revision-block replacement for this repo.  
Human-readable summary + machine-readable source of truth in `engineering_log.jsonl`.

## AI Update Protocol (Required)
1. For every change to code/content/config, append one JSON record to `engineering_log.jsonl`.
2. Add one summary row to the table below with the same `entry_id`.
3. Do not edit or delete old log records. If needed, append a new record with `change_type: "correction"` or `change_type: "supersede"`.
4. If data is uncertain, keep the entry and set `confidence: "inferred"` with a clear note.
5. Always list changed files and verification performed (or explicitly state not run).

## Record Fields (JSONL)
- `entry_id`: unique id (`YYYYMMDD-HHMMSS-actor-slug`)
- `timestamp`: ISO-8601 with timezone
- `actor`: human name or bot id
- `change_type`: `feature|fix|refactor|process|docs|correction|supersede`
- `status`: `completed|partial|reverted|superseded`
- `summary`: short sentence
- `files`: changed files
- `verification`: tests/checks run (or `"not_run"`)
- `confidence`: `confirmed|inferred`
- `notes`: optional context/tradeoffs

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

