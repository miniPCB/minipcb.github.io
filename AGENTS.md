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
- For any code/content change, append a log record to `agents_log.jsonl` and add a short summary row to `agents_log.md`.
- Every new log record must include per-file edit statements: file name plus 1+ concise statements of what was changed in that file.
- Treat `agents_log.jsonl` as append-only history; never rewrite old records (add a new correction/supersede record instead).

## Tools

- Prefer `rg` for searching file contents and `rg --files` for finding files.
- Narrow searches to relevant directories and file types when possible.
- Use fixed-string search (`rg -F`) for literal text, filenames, URLs, and part numbers. Use regex when matching variations.
- Use `apply_patch` for small, targeted edits.
- Use scripts for repetitive changes across many files. Inspect the resulting diff for unintended changes.
- Use `git diff --stat` to review the scope of changes and `git diff` to review their contents.
- Use existing repository build and validation tools when available.
- Use a browser, when available, to verify changes to page layout and interactive behavior.
- Do not perform broad replacements without first inspecting the matches.

### Search examples

These examples assume execution from the repository root.

- Find files associated with a board:
  `rg --files | rg '04A-006'`

- Find a literal board identifier in file contents:
  `rg -n -F '04A-006'`

- Search HTML files for literal text:
  `rg -n -F -g '*.html' 'Circuit boards for electronics education'`

- Find HTML link and asset references:
  `rg -n -g '*.html' '(href|src)\s*='`

- Find Markdown links and images:
  `rg -n -g '*.md' '!?\[[^]]*\]\([^)]+\)'`

- Find unfinished-work markers:
  `rg -n '\b(TODO|FIXME|XXX)\b'`

- Find references without searching agent logs:
  `rg -n -F -g '!agents_log.*' '04A-006'`

Search patterns help locate candidates; they do not establish that links,
HTML, Markdown, or JavaScript are valid.

## Testing
- Run relevant tests if available.
- If not run, say so.

## Notes
- Avoid touching files not needed for the task.
