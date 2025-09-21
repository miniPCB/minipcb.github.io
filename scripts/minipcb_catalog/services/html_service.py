# minipcb_catalog/services/html_service.py
"""
HTMLService — section-aware operations for miniPCB Catalog.

Centralizes how we:
- Extract/apply section content using comment markers from constants.SECTIONS
- Ensure missing sections exist (idempotent migration support)
- Get/set metadata (<title>, keywords, status/slogan)
- Get/set image src by stable <img id="...">
- Prettify (light) the HTML without changing semantic content
- Extract the first <table> in <main> (Collection pages)

This wraps the low-level helpers in utils.html so the rest of the app
doesn't need to know about markers or regex details.
"""

from __future__ import annotations

from typing import Dict, Any, List, Tuple

from .. import constants
from ..utils import html as H


class HTMLService:
    # ---------------------------------------------------------------------
    # Sections (comment-bounded as specified in constants.SECTIONS)
    # ---------------------------------------------------------------------

    def extract_sections(self, page_html: str) -> Dict[str, str]:
        """
        Return a dict {section_id: inner_html} for all known sections.
        Missing blocks yield the default HTML from constants.SECTION_DEFAULT_HTML.
        """
        out: Dict[str, str] = {}
        S = constants.SECTIONS
        D = constants.SECTION_DEFAULT_HTML
        for sid, spec in S.items():
            if "begin" in spec and "end" in spec:
                out[sid] = H.get_block_inner(
                    page_html or "",
                    spec["begin"],
                    spec["end"],
                    D.get(sid, "")
                ).strip()
        return out

    def apply_sections(self, page_html: str, sections: Dict[str, str]) -> str:
        """
        Replace (or create) the inner HTML for any provided sections and return updated full HTML.
        Only applies to comment-bounded sections (those that have begin/end markers).
        """
        html = page_html or ""
        S = constants.SECTIONS
        D = constants.SECTION_DEFAULT_HTML
        for sid, new_inner in sections.items():
            spec = S.get(sid)
            if not spec or "begin" not in spec or "end" not in spec:
                continue
            html = H.set_block_inner(
                html,
                spec["begin"],
                spec["end"],
                new_inner,
                D.get(sid, "")
            )
        return html

    def ensure_section(self, page_html: str, section_id: str) -> str:
        """
        Ensure a given section exists (create an empty/default block if missing).
        No-op if the section already exists.
        """
        spec = constants.SECTIONS.get(section_id)
        if not spec or "begin" not in spec or "end" not in spec:
            return page_html
        default_inner = constants.SECTION_DEFAULT_HTML.get(section_id, "")
        return H.ensure_block(page_html or "", spec["begin"], spec["end"], default_inner)

    # ---------------------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------------------

    def get_title(self, page_html: str) -> str:
        return H.get_title(page_html or "")

    def set_title(self, page_html: str, new_title: str) -> str:
        """
        Safe title setter; uses utils.html to avoid duplicated/garbled titles.
        """
        return H.set_title(page_html or "", new_title or "")

    def get_keywords(self, page_html: str) -> str:
        return H.get_keywords(page_html or "")

    def set_keywords(self, page_html: str, kw: str) -> str:
        return H.set_keywords(page_html or "", kw or "")

    def get_status_tag(self, page_html: str) -> str:
        """
        Reads the <p class="slogan">…</p> text (used as "Slogan"/status tag).
        """
        return H.get_status_tag(page_html or "")

    def set_status_tag(self, page_html: str, txt: str) -> str:
        """
        Sets (or inserts into <header>) the <p class="slogan">…</p> text.
        """
        return H.set_status_tag(page_html or "", txt or "")

    # ---------------------------------------------------------------------
    # Images by known ids (schematic/layout)
    # ---------------------------------------------------------------------

    def get_image_src(self, page_html: str, kind: str) -> str:
        """
        kind: keys in constants.SECTIONS that carry a 'css' value referencing an <img id="...">,
              typically "schematic_img" or "layout_img" depending on your constants.
        """
        spec = constants.SECTIONS.get(kind, {})
        css = spec.get("css", "")
        # We support the convention img#schematic / img#layout
        if css == "img#schematic":
            return H.get_img_src_by_id(page_html or "", "schematic")
        if css == "img#layout":
            return H.get_img_src_by_id(page_html or "", "layout")
        return ""

    def set_image_src(self, page_html: str, kind: str, src: str) -> str:
        spec = constants.SECTIONS.get(kind, {})
        css = spec.get("css", "")
        if css == "img#schematic":
            return H.set_img_src_by_id(page_html or "", "schematic", src or "")
        if css == "img#layout":
            return H.set_img_src_by_id(page_html or "", "layout", src or "")
        return page_html

    # ---------------------------------------------------------------------
    # Formatting
    # ---------------------------------------------------------------------

    def prettify(self, html: str) -> str:
        """
        Lightweight "pretty print" that keeps content intact:
        - Normalizes whitespace between tags
        - Indents nested blocks
        - Preserves <script>/<style> contents
        This is implemented in utils.html consumers (MainWindow calls into this).
        """
        # Reuse the same logic as earlier version by performing a simple indentation pass.
        # Implemented inline to avoid adding a new dependency.
        import re  # local import to keep module surface small

        if not html:
            return html

        placeholders: List[str] = []

        def _protect(m):
            placeholders.append(m.group(0))
            return f"__PRESERVE_BLOCK_{len(placeholders)-1}__"

        safe = re.sub(r'(<(script|style)[^>]*>.*?</\2>)', _protect, html, flags=re.I | re.S)
        safe = re.sub(r'>\s+<', '><', safe)
        safe = re.sub(r'(</(div|section|header|footer|nav|main|ul|ol|li|table|thead|tbody|tr)>)',
                      r'\1\n', safe, flags=re.I)
        safe = re.sub(r'(<(div|section|header|footer|nav|main|ul|ol|li|table|thead|tbody|tr)[^>]*>)',
                      r'\n\1\n', safe, flags=re.I)
        safe = re.sub(r'\n{3,}', '\n\n', safe)

        lines = [ln for ln in safe.splitlines()]
        out: List[str] = []
        indent = 0
        opens = re.compile(r'<(div|section|header|footer|nav|main|ul|ol|table|thead|tbody|tr)\b[^>]*>', re.I)
        closes = re.compile(r'</(div|section|header|footer|nav|main|ul|ol|table|thead|tbody|tr)>', re.I)
        singleline = re.compile(r'<(li|tr|td|th)\b[^>]*>.*?</\1>', re.I)

        for raw in lines:
            ln = raw.strip()
            if not ln:
                continue
            if closes.match(ln) and not opens.search(ln):
                indent = max(0, indent - 1)
            out.append(('  ' * indent) + ln)
            if opens.search(ln) and not closes.search(ln) and not singleline.search(ln):
                indent += 1

        pretty = "\n".join(out).strip()

        def _restore(m):
            idx = int(m.group(1))
            return placeholders[idx] if 0 <= idx < len(placeholders) else m.group(0)

        pretty = re.sub(r'__PRESERVE_BLOCK_(\d+)__', _restore, pretty)
        return pretty + "\n"

    # ---------------------------------------------------------------------
    # Collection pages — extract first table in <main>
    # ---------------------------------------------------------------------

    def extract_collection_table(self, page_html: str) -> Tuple[List[str], List[List[str]]]:
        """
        Convenience proxy to utils.html.extract_main_table.
        Returns (headers, rows) for the first table within <main>.
        """
        return H.extract_main_table(page_html or "")
