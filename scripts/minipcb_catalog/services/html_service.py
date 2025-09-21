# minipcb_catalog/services/html_service.py
"""
HTMLService — section-aware operations for miniPCB Catalog.

This service supports two page styles:

1) Marker-based sections (constants.SECTIONS with begin/end markers) using utils.html (H).
2) Fallback id-based sections: <div id="details" class="tab-content">…</div>

MainWindow can freely call ensure_section/apply_sections and this service will do the right thing
depending on what’s present in the page and/or in constants.SECTIONS.

It also provides basic metadata helpers, a lightweight prettifier, and optional image/status helpers.
"""

from __future__ import annotations

import re
from typing import Dict, Any

from .. import constants
from ..utils import html as H


class HTMLService:
    # -------------------- Metadata --------------------

    def get_title(self, page_html: str) -> str:
        # Prefer utils.html if available; fall back to regex
        try:
            t = H.get_title(page_html)
            if t is not None:
                return t
        except Exception:
            pass
        m = re.search(r'<title[^>]*>(.*?)</title>', page_html, re.I | re.S)
        return re.sub(r'\s+', ' ', m.group(1)).strip() if m else ""

    def set_title(self, page_html: str, new_title: str) -> str:
        try:
            return H.set_title(page_html, new_title)
        except Exception:
            pass
        if not new_title:
            return page_html
        def repl(m): return m.group(1) + new_title + m.group(3)
        if re.search(r'(<title[^>]*>)(.*?)(</title>)', page_html, re.I | re.S):
            return re.sub(r'(<title[^>]*>)(.*?)(</title>)', repl, page_html, count=1, flags=re.I | re.S)
        return page_html

    def get_keywords(self, page_html: str) -> str:
        try:
            kw = H.get_keywords(page_html)
            if kw is not None:
                return kw
        except Exception:
            pass
        m = re.search(r'<meta\s+name=["\']keywords["\']\s+content=["\'](.*?)["\']', page_html, re.I | re.S)
        return m.group(1).strip() if m else ""

    def set_keywords(self, page_html: str, kw: str) -> str:
        try:
            return H.set_keywords(page_html, kw)
        except Exception:
            pass
        if not kw:
            return page_html
        if re.search(r'<meta\s+name=["\']keywords["\']', page_html, re.I):
            return re.sub(
                r'(<meta\s+name=["\']keywords["\']\s+content=["\'])(.*?)("["\'])',
                r'\1' + re.escape(kw) + r'\3', page_html, count=1, flags=re.I
            )
        return page_html

    # Optional helpers; MainWindow does not require them but they’re harmless to keep.
    def get_status_tag(self, page_html: str) -> str:
        try:
            return H.get_status_tag(page_html)
        except Exception:
            return ""

    def set_status_tag(self, page_html: str, txt: str) -> str:
        try:
            return H.set_status_tag(page_html, txt)
        except Exception:
            return page_html

    # -------------------- Section handling --------------------

    def _has_marker_spec(self, section_id: str) -> bool:
        spec = constants.SECTIONS.get(section_id)
        return bool(spec and "begin" in spec and "end" in spec)

    def ensure_section(self, page_html: str, section_id: str) -> str:
        """
        Ensure the section exists. If the section is defined in constants.SECTIONS with
        markers, use utils.html ensure_block; otherwise ensure a <div id="..."> block exists.
        """
        if self._has_marker_spec(section_id):
            spec = constants.SECTIONS[section_id]
            default_inner = constants.SECTION_DEFAULT_HTML.get(section_id, "")
            return H.ensure_block(page_html, spec["begin"], spec["end"], default_inner)

        # Fallback: id-based div
        if re.search(rf'<div[^>]+id=["\']{re.escape(section_id)}["\']', page_html, re.I):
            return page_html
        block = f'\n<div id="{section_id}" class="tab-content"></div>\n'
        if "</main>" in page_html:
            return page_html.replace("</main>", block + "</main>", 1)
        return page_html + block

    def apply_sections(self, page_html: str, updates: Dict[str, str]) -> str:
        """
        Apply inner HTML for the given sections.
        - If section has marker spec: use utils.html set_block_inner
        - Else: replace inner of <div id="section">…</div> (create if missing)
        """
        html = page_html

        for section_id, new_inner in updates.items():
            if self._has_marker_spec(section_id):
                spec = constants.SECTIONS[section_id]
                default_inner = constants.SECTION_DEFAULT_HTML.get(section_id, "")
                html = H.set_block_inner(html, spec["begin"], spec["end"], new_inner, default_inner)
                continue

            # Fallback id-based replace (create if missing)
            rx = re.compile(
                rf'(<div[^>]+id=["\']{re.escape(section_id)}["\'][^>]*>)(.*?)(</div>)',
                re.I | re.S
            )
            if rx.search(html):
                html = rx.sub(rf'\1{new_inner}\3', html, count=1)
            else:
                html += f'\n<div id="{section_id}" class="tab-content">{new_inner}</div>\n'

        return html

    # Convenience for bulk extraction if you use markers; not used by MainWindow directly.
    def extract_sections(self, page_html: str) -> Dict[str, str]:
        """
        Return {section_id: inner_html} for sections that have begin/end markers.
        If a section doesn’t have markers, it’s skipped here (MainWindow handles id-based parsing
        on its own where needed).
        """
        out: Dict[str, str] = {}
        S = constants.SECTIONS
        D = constants.SECTION_DEFAULT_HTML
        for sid, spec in S.items():
            if "begin" in spec and "end" in spec:
                out[sid] = H.get_block_inner(
                    page_html,
                    spec["begin"],
                    spec["end"],
                    D.get(sid, "")
                ).strip()
        return out

    # -------------------- Images --------------------

    def get_image_src(self, page_html: str, kind: str) -> str:
        """
        kind: "schematic_img" or "layout_img" as defined in constants.SECTIONS (css id based)
        """
        spec = constants.SECTIONS.get(kind, {})
        if spec.get("css") == "img#schematic":
            return H.get_img_src_by_id(page_html, "schematic")
        if spec.get("css") == "img#layout":
            return H.get_img_src_by_id(page_html, "layout")
        return ""

    def set_image_src(self, page_html: str, kind: str, src: str) -> str:
        spec = constants.SECTIONS.get(kind, {})
        if spec.get("css") == "img#schematic":
            return H.set_img_src_by_id(page_html, "schematic", src)
        if spec.get("css") == "img#layout":
            return H.set_img_src_by_id(page_html, "layout", src)
        return page_html

    # -------------------- Prettify --------------------

    def prettify(self, html: str) -> str:
        """
        Lightweight "pretty print" that keeps content intact:
        - Normalizes whitespace between tags
        - Indents nested block-ish tags
        - Keeps script/style contents untouched
        No external dependencies; not a full HTML parser by design.
        """
        if not html:
            return html

        # Protect script/style content
        placeholders = []
        def _protect(m):
            placeholders.append(m.group(0))
            return f"__PRESERVE_BLOCK_{len(placeholders)-1}__"
        safe = re.sub(r'(<(script|style)[^>]*>.*?</\2>)', _protect, html, flags=re.I | re.S)

        # Collapse extraneous spaces between tags
        safe = re.sub(r'>\s+<', '><', safe)

        # Add newlines around block tags to help indentation
        safe = re.sub(r'(</(div|section|header|footer|nav|main|ul|ol|li|table|thead|tbody|tr)>)', r'\1\n', safe, flags=re.I)
        safe = re.sub(r'(<(div|section|header|footer|nav|main|ul|ol|li|table|thead|tbody|tr)[^>]*>)', r'\n\1\n', safe, flags=re.I)

        # Normalize multiple newlines
        safe = re.sub(r'\n{3,}', '\n\n', safe)

        # Indentation
        lines = [ln for ln in safe.splitlines()]
        out = []
        indent = 0
        opens = re.compile(r'<(div|section|header|footer|nav|main|ul|ol|table|thead|tbody|tr)\b[^>]*>', re.I)
        closes = re.compile(r'</(div|section|header|footer|nav|main|ul|ol|table|thead|tbody|tr)>', re.I)
        singleline = re.compile(r'<(li|tr|td|th)\b[^>]*>.*?</\1>', re.I)

        for raw in lines:
            ln = raw.strip()
            if not ln:
                continue
            # decrease indent if this line starts with a closing tag
            if closes.match(ln) and not opens.search(ln):
                indent = max(0, indent - 1)
            out.append(('  ' * indent) + ln)
            # increase indent if this line ends with an opening tag that isn't single-line closed
            if opens.search(ln) and not closes.search(ln) and not singleline.search(ln):
                indent += 1

        pretty = "\n".join(out).strip()

        # Restore protected blocks
        def _restore(m):
            idx = int(m.group(1))
            return placeholders[idx] if 0 <= idx < len(placeholders) else m.group(0)
        pretty = re.sub(r'__PRESERVE_BLOCK_(\d+)__', _restore, pretty)
        return pretty + "\n"

    # Inside HTMLService
    def get_title(self, page_html: str) -> str:
        """
        Return the first <title>…</title> content, trimmed. Empty string if none.
        """
        m = re.search(r'<title\b[^>]*>(.*?)</title>', page_html, flags=re.I | re.S)
        if not m:
            return ""
        # Collapse internal whitespace to a single space
        txt = re.sub(r'\s+', ' ', m.group(1)).strip()
        return txt

    def set_title(self, page_html: str, new_title: str) -> str:
        """
        Normalize to a single <title>…</title> in <head>. Removes any/all existing title tags
        (and any orphaned remnants), then inserts one canonical title.
        """
        if not new_title:
            return page_html

        html = page_html

        # 1) Remove ALL existing <title>…</title> (handles orphans/duplicates, with whitespace)
        html = re.sub(r'\s*<title\b[^>]*>.*?</title>\s*', '\n', html, flags=re.I | re.S)

        # 2) Also defensively remove any dangling plain-text '</title>' artifacts (from prior bugs)
        html = re.sub(r'\s*</title>\s*', '\n', html, flags=re.I)

        # 3) Insert a single <title> right after <head ...>
        head_open = re.search(r'<head\b[^>]*>', html, flags=re.I)
        title_block = f'\n  <title>{new_title}</title>\n'

        if head_open:
            insert_at = head_open.end()
            html = html[:insert_at] + title_block + html[insert_at:]
            return html

        # 4) If there is no <head>, create one (rare but safe)
        # Try to put it before the first <body>; otherwise prepend
        body_open = re.search(r'<body\b[^>]*>', html, flags=re.I)
        head_full = f'<head>{title_block}</head>\n'
        if body_open:
            pos = body_open.start()
            html = html[:pos] + head_full + html[pos:]
        else:
            html = head_full + html

        return html
