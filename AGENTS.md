# AGENTS.md

## Purpose
Instructions for Codex or other agents working in this repo.

## Priorities
- Preserve existing behavior unless requested.
- Prefer minimal, targeted edits.
- Keep changes consistent with existing style.

## Workflow
- Read relevant files before editing.
- Use the least invasive change that solves the task.
- Mention any assumptions.
- For any code/content change, append a log record to `engineering_log.jsonl` and add a short summary row to `engineering_log.md`.
- Treat `engineering_log.jsonl` as append-only history; never rewrite old records (add a new correction/supersede record instead).

## Tools
- Prefer `rg` for search.
- Use `apply_patch` for small edits.

## Testing
- Run relevant tests if available.
- If not run, say so.

## Notes
- Avoid touching files not needed for the task.
