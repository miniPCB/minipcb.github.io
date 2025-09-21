# minipcb_catalog/constants.py
"""
Centralized constants for miniPCB Catalog (website editor).

This module is the single source of truth for:
- Which sections a page has and how they’re delimited in HTML
- CSS selectors for schematic/layout images
- Validation & maturity scoring weights and thresholds
- File scanning patterns and special-case rules (e.g., catlog_* pages)
- Default settings scaffold

If your site template changes, update this file and the rest of the app
(services/html_service.py, migration_service.py, UI tabs) will follow.
"""

from __future__ import annotations

from typing import Final, Dict, Any
import re
from pathlib import Path

APP_NAME: Final[str] = "miniPCB Catalog"

# ---- File discovery & special cases ---------------------------------------

# HTML pages to include when scanning the repo
HTML_GLOBS: Final[tuple[str, ...]] = ("**/*.html", "**/*.htm")

# Paths to ignore while scanning (kept generous; tweak for your repo)
IGNORE_GLOBS: Final[tuple[str, ...]] = (
    "**/.git/**",
    "**/.github/**",
    "**/.venv/**",
    "**/node_modules/**",
    "**/_site/**",
    "**/dist/**",
    "**/build/**",
    "**/.minipcb/**",   # runtime analytics / cache
)

# Files matching this pattern should have all tabs disabled except Review
# (Your prior rule: catlog_* pages are review-only)
CATLOG_REVIEW_ONLY: Final[re.Pattern[str]] = re.compile(r"^catlog_", re.IGNORECASE)

# ---- Section definitions ---------------------------------------------------
# For each logical section, define how it is found/created in the DOM.
# Comment-bounded blocks are preferred for stability across edits.

def _mk_block(label: str) -> Dict[str, str]:
    return {
        "begin": f"<!-- BEGIN: {label} -->",
        "end":   f"<!-- END: {label} -->",
    }

SECTIONS: Final[Dict[str, Dict[str, Any]]] = {
    # Text/content sections (comment-bounded blocks)
    "details":              _mk_block("Details"),
    "circuit_description":  _mk_block("Circuit Description"),
    "resources":            _mk_block("Resources"),
    "downloads":            _mk_block("Downloads"),
    # Optional, but we always ensure presence to avoid UI crashes
    "dtp":                  _mk_block("Developmental Test Plan (DTP)"),

    # Images (selected via CSS)
    "schematic_img": {"css": "img#schematic"},   # <img id="schematic" ...>
    "layout_img":    {"css": "img#layout"},      # <img id="layout" ...>
}

# Order for UI tabs / export consistency
SECTION_ORDER: Final[tuple[str, ...]] = (
    "details",
    "circuit_description",
    "resources",
    "downloads",
    "dtp",
)

# Minimal DOM fallbacks to inject during migration when missing sections are created
SECTION_DEFAULT_HTML: Final[Dict[str, str]] = {
    "details": "<p></p>",
    "circuit_description": "<p></p>",
    "resources": "<ul>\n  <li></li>\n</ul>",
    "downloads": "<ul>\n  <li></li>\n</ul>",
    "dtp": "<p></p>",
}

# ---- Metadata selectors ----------------------------------------------------

TITLE_SELECTOR: Final[str] = "title"              # <title>...</title>
KEYWORDS_META_SELECTOR: Final[str] = 'meta[name="keywords"]'
STATUS_TAG_SELECTOR: Final[str] = "span.status-tag"  # your color-coded chip/span

# ---- Validation & maturity -------------------------------------------------

# Required sections for a page to be considered non-placeholder
REQUIRED_SECTIONS: Final[tuple[str, ...]] = ("details", "circuit_description")

# Readability & word-count guidance per section (used by maturity_service)
WORD_COUNT_RANGES: Final[Dict[str, tuple[int, int]]] = {
    "details": (60, 250),
    "circuit_description": (150, 600),
    # optional sections can be looser / omitted
}

# Maturity scoring weights (sum to ~100). Adjust here to tune behavior.
MATURITY_WEIGHTS: Final[Dict[str, int]] = {
    "required_sections_present": 30,
    "word_counts_ok":           10,
    "readability_ok":            8,
    "images_present":           12,
    "image_alt_present":         6,
    "links_ok":                  8,
    "keywords_ok":               6,
    "no_todos":                  5,
    "recently_edited":           5,
    "unique_title":              5,
    "dom_valid":                 5,
}

# Level thresholds
#   0–24 → Level 0 (Placeholder)
#  25–59 → Level 1 (Immature)
#  60–84 → Level 2 (Mature)
#  85–100 (+ locked) → Level 3 (Locked)
MATURITY_LEVEL_THRESHOLDS: Final[Dict[int, int]] = {
    0: 0,
    1: 25,
    2: 60,
    3: 85,
}

# Recency window (days) for “recently_edited” credit
RECENT_EDIT_DAYS: Final[int] = 90

# ---- Footer/year normalization (shared pattern) ----------------------------

YEAR_RE: Final[re.Pattern[str]] = re.compile(r"(?:19|20)\d{2}")
RANGE_SEP_CLASS: Final[str] = r"(?:\u2013|–|—|-)"  # en/em dashes and hyphen

# ---- Defaults / settings scaffold -----------------------------------------

DEFAULT_AUTOSAVE_SECONDS: Final[int] = 60
DEFAULT_THEME: Final[str] = "dark"

DEFAULT_SETTINGS: Final[Dict[str, Any]] = {
    "theme": DEFAULT_THEME,
    "autosave_interval_s": DEFAULT_AUTOSAVE_SECONDS,
    "analytics_enabled": True,
    "linkcheck_online": False,   # offline format checks by default
    # paths as strings (resolved at runtime relative to project root)
    "images_root": "images",
    "export_single_path": "minipcb_catalog_single.py",
}

# ---- Helpers ---------------------------------------------------------------

def is_catlog_review_only(path: Path) -> bool:
    """Return True if the given file should be review-only (tabs disabled)."""
    return CATLOG_REVIEW_ONLY.search(path.name) is not None
