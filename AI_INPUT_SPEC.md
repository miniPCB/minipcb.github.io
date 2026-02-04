---
title: "AI-Input Specification v2: miniPCB Website Editor (Single-File, Template-Driven)"
subtitle: "Template-driven editor and AI-assisted content workflow"
author: "miniPCB"
version: "v2"
date: "2026-02-04"
status: "Draft"
---

AI-Input Specification v2: miniPCB Website Editor (Single-File, Template-Driven)

Introduction
This document defines the AI-input specification for the miniPCB.com website editor. It describes a template-driven, single-file editor that generates complete HTML pages from structured form inputs and supports type-specific editing for board and collection pages. The editor expands the miniPCB project by adding a consistent workflow for page creation, updates, and content standardization. It also sets the foundation for an AI-assisted interface that can draft and update page content in a controlled, schema-driven way.

1) Mission
Create a single-file editor (website_editor.html) that embeds HTML templates for each page type and overwrites full HTML files when the user runs an Update command. The editor must provide a large, structured form that auto-adapts to page type and includes a Template Editor for shared head/footer content (analytics, metadata defaults, copyright).

2) Sandbox Scope
- Draft workspace is draft/.
- Left pane lists all HTML files in draft/ (clean path listing).
- Output overwrites the full file in draft/ when Update runs.

3) File Types (Canonical Examples)
- Board file: draft/04B/04B-005.html
- Collection file: draft/collections/transistor-amplifiers.html

4) Embedded Templates
Templates are stored inside website_editor.html and used to regenerate full file output.

4.1) Board Template
Fields required to generate:
- Head: title, keywords, description, analytics script
- Nav: list of links
- Header: H1 + slogan
- Tabs: list + section bodies
- Sections typed:
  - Details (label/value rows)
  - Description (rich text)
  - Schematic/Layout (image lists)
  - Downloads (label+href list)
  - Videos (iframe list)
  - Revisions (table rows)
  - Resources (rich content / video list)
  - AI Seeds (JSON script)

4.2) Collection Template
Fields required:
- Head: title, keywords
- Nav: list of links
- Header: H1
- Table rows: Part No, Title, Href, Pieces per Panel

4.3) Template Editor (Global)
A dedicated Template Editor area in the form:
- Google Analytics / tag script (editable)
- Default metadata (keywords/description)
- Default footer (copyright text)
- Default CSS/JS includes
- Version string/date stamps
- Optional defaults per page type

5) Update Behavior
- Update command overwrites the entire HTML file with template-generated output.
- No partial edits; template output is the source of truth.

6) Editor UI & Commands
We need a safe, cool command execution UI that feels right for miniPCB.com.

Proposed UI
- Command Bar + Terminal Pane:
  - Command input line with history.
  - Output log area.
  - Command palette for common actions.
- Actions (buttons/icons):
  - Update (write full HTML)
  - Reload (refresh from file)
  - Validate (check required fields)
  - Export (download HTML)
  - AI Assist (open chat panel)
- AI Chat = Terminal (same pane)

7) AI Assist: High-Quality Conversation
Goal: AI helps create and edit pages with high conversation/quality ratio.
- AI is guided by the form schema (not free-form).
- AI creates/edits specific fields, not arbitrary HTML.
- AI proposes updates to:
  - Meta fields
  - Section bodies
  - Download/video lists
  - Collection rows
  - Revision entries
  - AI seed JSON
- AI response must be structured into field updates (not raw prose).

AI Output Format (proposal)
- JSON patches like:
  - set.meta.title, set.header.slogan, add.section.videos, append.collection.rows
- AI can ask clarifying questions when required fields are missing.

8) Vercel Usage (From Repo)
We host a Vercel OpenAI proxy in proxy-vercel/.

Deployment (no CLI):
1) Create a Vercel project pointing to this repo.
2) Set Root Directory = proxy-vercel.
3) Set environment variable:
   - OPENAI_API_KEY (required)
4) Deploy.

Endpoints:
- GET /api/health
- GET /api/models
- POST /api/review
- POST /api/suggest
- POST /api/chat
- POST /api/create

Frontend Config (Test Base 2026 Preferences):
API Base URL = https://minipcb-github-io.vercel.app/api

GitHub Pages stays static, and Vercel handles the proxy.

9) Visual Style
- UI styling must remain consistent with the current website_editor.html (colors, typography, layout, and overall aesthetic).

10) Open Decisions
- Command UI style (palette vs terminal-only).
- Template defaults: where they live in the UI and how they apply.
- How Update handles optional/hidden sections and ordering.
- AI patch format details and safety rules.
