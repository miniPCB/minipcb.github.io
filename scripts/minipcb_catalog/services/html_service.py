from __future__ import annotations

import re
from typing import Optional, Dict

# --------- Regexes (DOTALL, non-greedy) ---------

_TITLE_RX = re.compile(r'(<title[^>]*>)(.*?)(</title>)', re.I | re.S)

# meta name="description"
_META_DESC_RX = re.compile(
    r'(<meta[^>]*\bname=["\']description["\'][^>]*\bcontent=["\'])(.*?)((["\'][^>]*>))',
    re.I | re.S,
)

# meta name="keywords"
_META_KEYS_RX = re.compile(
    r'(<meta[^>]*\bname=["\']keywords["\'][^>]*\bcontent=["\'])(.*?)((["\'][^>]*>))',
    re.I | re.S,
)

# <head ...>
_HEAD_OPEN_RX = re.compile(r'(<head[^>]*>)', re.I)

# <main ...>
_MAIN_OPEN_RX = re.compile(r'(<main[^>]*>)', re.I)

# Image tag with a specific id
def _compile_img_tag_rx(img_id: str) -> re.Pattern[str]:
    esc = re.escape(img_id)
    # whole <img ...id="img_id"...> tag
    return re.compile(rf'(<img[^>]*\bid=["\']{esc}["\'][^>]*>)', re.I | re.S)

# generic attribute matchers (run against the single <img> tag string)
_SRC_RX = re.compile(r'(\bsrc=["\'])([^"\']*)(["\'])', re.I)
_ALT_RX = re.compile(r'(\balt=["\'])([^"\']*)(["\'])', re.I)

# Section <div id="...">...</div>
def _compile_section_rx(section_id: str) -> re.Pattern[str]:
    esc = re.escape(section_id)
    return re.compile(
        rf'(<div[^>]*\bid=["\']{esc}["\'][^>]*>)(.*?)(</div>)',
        re.I | re.S,
    )


# --------- Sanitizer for Qt-rich-text & inline styles ---------

_DOCTYPE_RX = re.compile(r'<!DOCTYPE[^>]*>\s*', re.I | re.S)
_HTML_WRAPPER_RX = re.compile(r'</?html[^>]*>', re.I)
_HEAD_BLOCK_RX = re.compile(r'<head[^>]*>.*?</head>', re.I | re.S)
_BODY_BLOCK_RX = re.compile(r'<body[^>]*>(.*?)</body>', re.I | re.S)
_META_ANY_RX = re.compile(r'<meta[^>]*>', re.I | re.S)
_STYLE_BLOCK_RX = re.compile(r'<style[^>]*>.*?</style>', re.I | re.S)
_INLINE_STYLE_RX = re.compile(r'\sstyle="[^"]*"', re.I)
_SPAN_OPEN_RX = re.compile(r'<span[^>]*>', re.I)
_SPAN_CLOSE_RX = re.compile(r'</span>', re.I)
_EMPTY_P_BR_RX = re.compile(r'<p[^>]*>\s*(?:<br\s*/?>)?\s*</p>', re.I | re.S)
_QT_MARKER_RX = re.compile(r'qrichtext|-qt-', re.I)  # quick detection

def sanitize_fragment(fragment: str) -> str:
    """Strip Qt's rich-text wrappers/doctype/styles and inline style junk.
    Keep semantic structure (p, ul/ol/li, b/strong/i/em, code/pre, h1..h6, tables)."""
    if not fragment:
        return ""

    f = fragment

    # If it looks like Qt rich text (doctype, qrichtext, or <body>), extract body first
    looks_qt = (
        _QT_MARKER_RX.search(f) is not None
        or _DOCTYPE_RX.search(f) is not None
        or '<body' in f.lower()
        or '<html' in f.lower()
    )

    if looks_qt:
        # Drop doctype & head; keep body inner if present
        f = _DOCTYPE_RX.sub('', f)
        f = _HEAD_BLOCK_RX.sub('', f)
        m = _BODY_BLOCK_RX.search(f)
        if m:
            f = m.group(1)
        # remove html wrappers if any remain
        f = _HTML_WRAPPER_RX.sub('', f)

    # Remove remaining meta/style blocks and inline style attrs
    f = _META_ANY_RX.sub('', f)
    f = _STYLE_BLOCK_RX.sub('', f)
    f = _INLINE_STYLE_RX.sub('', f)

    # Remove span wrappers (keep their inner text/children)
    f = _SPAN_OPEN_RX.sub('', f)
    f = _SPAN_CLOSE_RX.sub('', f)

    # Remove empty paragraphs like <p><br></p> or whitespace-only
    f = _EMPTY_P_BR_RX.sub('', f)

    # Basic tidy: strip surrounding whitespace
    f = f.strip()

    return f


# --------- Title helpers (multi-line safe, no re.escape on content) ---------

def get_title(html: str) -> str:
    m = _TITLE_RX.search(html or "")
    if not m:
        return ""
    import re as _re
    return _re.sub(r"\s+", " ", (m.group(2) or "")).strip()


def set_title(html: str, text: str) -> str:
    """Replace or insert <title>…</title> using callable replacement to avoid
    backreference issues. Never use re.escape on user text.
    """
    def repl(m):
        return m.group(1) + (text or "") + m.group(3)

    if _TITLE_RX.search(html or ""):
        return _TITLE_RX.sub(repl, html, count=1)

    # No <title>: insert inside <head> if present
    h = _HEAD_OPEN_RX.search(html or "")
    if h:
        idx = h.end(1)
        return (html or "")[:idx] + f"<title>{text or ''}</title>" + (html or "")[idx:]

    # No <head>: fail-safe append
    return (html or "") + f"<head><title>{text or ''}</title></head>"


# --------- Meta description helpers ---------

def get_meta_description(html: str) -> str:
    m = _META_DESC_RX.search(html or "")
    return (m.group(2) or "").strip() if m else ""


def set_meta_description(html: str, content: str) -> str:
    """Replace or insert <meta name="description" content="...">."""
    def repl(m):
        return m.group(1) + (content or "") + m.group(3)

    if _META_DESC_RX.search(html or ""):
        return _META_DESC_RX.sub(repl, html, count=1)

    h = _HEAD_OPEN_RX.search(html or "")
    tag = f'<meta name="description" content="{content or ""}">'
    if h:
        idx = h.end(1)
        return (html or "")[:idx] + tag + (html or "")[idx:]
    return (html or "") + f"<head>{tag}</head>"


# --------- Meta keywords helpers ---------

def get_meta_keywords(html: str) -> str:
    m = _META_KEYS_RX.search(html or "")
    return (m.group(2) or "").strip() if m else ""


def set_meta_keywords(html: str, content: str) -> str:
    """Replace or insert <meta name="keywords" content="...">."""
    def repl(m):
        return m.group(1) + (content or "") + m.group(3)

    if _META_KEYS_RX.search(html or ""):
        return _META_KEYS_RX.sub(repl, html, count=1)

    h = _HEAD_OPEN_RX.search(html or "")
    tag = f'<meta name="keywords" content="{content or ""}">'
    if h:
        idx = h.end(1)
        return (html or "")[:idx] + tag + (html or "")[idx:]
    return (html or "") + f"<head>{tag}</head>"


# --------- Legacy alias helpers (compat names used by MainWindow) ---------

def get_description(html: str) -> str:
    return get_meta_description(html)

def set_description(html: str, content: str) -> str:
    return set_meta_description(html, content)

def get_keywords(html: str) -> str:
    return get_meta_keywords(html)

def set_keywords(html: str, content: str) -> str:
    return set_meta_keywords(html, content)


# --------- Section helpers (used by MainWindow) ---------

def get_section(html: str, section_id: str) -> str:
    """Return the inner HTML of <div id="{section_id}">…</div>, or '' if not found."""
    rx = _compile_section_rx(section_id)
    m = rx.search(html or "")
    return (m.group(2) if m else "") or ""

def set_section(html: str, section_id: str, body_html: str) -> str:
    """Replace or create <div id="{section_id}">…</div> with body_html."""
    rx = _compile_section_rx(section_id)
    clean = sanitize_fragment(body_html or "")

    def repl(m):
        return m.group(1) + clean + m.group(3)

    if rx.search(html or ""):
        return rx.sub(repl, html, count=1)

    # Not found: create a new section block. Prefer appending inside <main>.
    block = f'<div id="{section_id}" class="tab-content">{clean}</div>'

    main_open = _MAIN_OPEN_RX.search(html or "")
    if main_open:
        idx = main_open.end(1)
        return (html or "")[:idx] + block + (html or "")[idx:]

    # Otherwise, insert before </body> if available
    if "</body>" in (html or ""):
        return (html or "").replace("</body>", block + "</body>", 1)

    # Fallback: append at end
    return (html or "") + block

def ensure_section(html: str, section_id: str) -> str:
    """Ensure a <div id="{section_id}">…</div> exists. If missing, create an empty one."""
    rx = _compile_section_rx(section_id)
    if rx.search(html or ""):
        return html or ""
    return set_section(html or "", section_id, "")

def apply_sections(html: str, updates: Dict[str, str]) -> str:
    """Apply multiple section updates, sanitizing each fragment first."""
    out = html or ""
    if not updates:
        return out
    for sid, body in updates.items():
        out = set_section(out, sid, body or "")
    return out


# --------- Image helpers (used by ImageService) ---------

def get_image_src(html: str, img_id: str) -> str:
    """Return the value of src for <img id="{img_id}" ...>, or '' if not found."""
    tag_rx = _compile_img_tag_rx(img_id)
    m = tag_rx.search(html or "")
    if not m:
        return ""
    tag = m.group(1)
    m_src = _SRC_RX.search(tag or "")
    return (m_src.group(2) if m_src else "") or ""

def get_image_alt(html: str, img_id: str) -> str:
    """Return the value of alt for <img id="{img_id}" ...>, or '' if not found."""
    tag_rx = _compile_img_tag_rx(img_id)
    m = tag_rx.search(html or "")
    if not m:
        return ""
    tag = m.group(1)
    m_alt = _ALT_RX.search(tag or "")
    return (m_alt.group(2) if m_alt else "") or ""

def _replace_img_tag(tag: str, *, src: Optional[str] = None, alt: Optional[str] = None) -> str:
    """Return a modified <img ...> tag string with src/alt updated or inserted."""
    out = tag
    if src is not None:
        if _SRC_RX.search(out):
            out = _SRC_RX.sub(lambda m: m.group(1) + (src or "") + m.group(3), out, count=1)
        else:
            out = re.sub(r'>\s*$', f' src="{src or ""}">', out, count=1)
    if alt is not None:
        if _ALT_RX.search(out):
            out = _ALT_RX.sub(lambda m: m.group(1) + (alt or "") + m.group(3), out, count=1)
        else:
            out = re.sub(r'>\s*$', f' alt="{alt or ""}">', out, count=1)
    return out

def set_image_src(html: str, img_id: str, src: str, alt: Optional[str] = None) -> str:
    """Update (or create) an <img id="{img_id}"> with the given src (and optional alt)."""
    tag_rx = _compile_img_tag_rx(img_id)
    m = tag_rx.search(html or "")
    if m:
        old_tag = m.group(1)
        new_tag = _replace_img_tag(old_tag, src=src, alt=alt)
        return (html or "")[:m.start(1)] + new_tag + (html or "")[m.end(1):]

    new_tag = f'<img id="{img_id}" src="{src or ""}"' + (f' alt="{alt}"' if alt is not None else "") + '>'
    main_open = _MAIN_OPEN_RX.search(html or "")
    if main_open:
        idx = main_open.end(1)
        return (html or "")[:idx] + new_tag + (html or "")[idx:]
    if "</body>" in (html or ""):
        return (html or "")[: html.rfind("</body>") ] + new_tag + "</body>"
    return (html or "") + new_tag

def set_image_alt(html: str, img_id: str, alt: str) -> str:
    """Update (or create) alt on <img id="{img_id}"> (leaves src unchanged)."""
    tag_rx = _compile_img_tag_rx(img_id)
    m = tag_rx.search(html or "")
    if m:
        old_tag = m.group(1)
        new_tag = _replace_img_tag(old_tag, alt=alt)
        return (html or "")[:m.start(1)] + new_tag + (html or "")[m.end(1):]
    new_tag = f'<img id="{img_id}" alt="{alt or ""}">'
    main_open = _MAIN_OPEN_RX.search(html or "")
    if main_open:
        idx = main_open.end(1)
        return (html or "")[:idx] + new_tag + (html or "")[idx:]
    if "</body>" in (html or ""):
        return (html or "")[: html.rfind("</body>") ] + new_tag + "</body>"
    return (html or "") + new_tag


# --------- One-stop head updater ---------

def update_head(
    html: str,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    keywords: Optional[str] = None,
) -> str:
    out = html or ""
    if title is not None:
        out = set_title(out, title)
    if description is not None:
        out = set_meta_description(out, description)
    if keywords is not None:
        out = set_meta_keywords(out, keywords)
    return out

# --- Add near other regexes ---
_MAIN_RX = re.compile(r'(<main[^>]*>)(.*?)(</main>)', re.I | re.S)

def replace_main_inner(html: str, inner_html: str) -> str:
    """Replace only the INNER content of the first <main>…</main> block.
    If <main> is missing, create one after <header> or before </body>.
    """
    clean_inner = sanitize_fragment(inner_html or "")
    m = _MAIN_RX.search(html or "")
    if m:
        return (html or "")[:m.start(2)] + clean_inner + (html or "")[m.end(2):]

    # No <main> present: try inserting after </header> if present
    if "</header>" in (html or ""):
        return (html or "").replace("</header>", "</header>\n<main>" + clean_inner + "</main>", 1)

    # Else insert before </body>, else append
    if "</body>" in (html or ""):
        return (html or "").replace("</body>", "<main>" + clean_inner + "</main></body>", 1)
    return (html or "") + "<main>" + clean_inner + "</main>"

def render_collection_main(title_h1: str, rows: list[dict]) -> str:
    """Return the <main> inner HTML for a collection page: a header + a table.
    rows: [{part:'04B-005', title:'Common Emitter Amplifier', href:'04B-005.html', pieces:'4'}, ...]
    """
    # sanitize cell content
    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    thead = (
        "<thead><tr>"
        "<th>Part No</th>"
        "<th>Title</th>"
        "<th>Pieces per Panel</th>"
        "</tr></thead>"
    )

    trows = []
    for r in rows:
        part = esc(r.get("part", ""))
        title = esc(r.get("title", ""))
        href = esc(r.get("href", "")) or f"{part}.html"
        pieces = esc(r.get("pieces", ""))
        trows.append(
            "<tr>"
            f"<td>{part}</td>"
            f"<td><a href=\"{href}\">{title}</a></td>"
            f"<td>{pieces}</td>"
            "</tr>"
        )
    tbody = "<tbody>" + "".join(trows) + "</tbody>"

    return (
        "<section>\n"
        f"  <h1>{esc(title_h1)}</h1>\n"
        '  <p class="slogan">04B-series miniPCB catalog</p>\n'
        "  <table>\n"
        f"    {thead}\n"
        f"    {tbody}\n"
        "  </table>\n"
        "</section>"
    )

# --------- Backward-compatible class API ---------

class HTMLService:
    """Compatibility wrapper exposing the old class API."""

    # Title
    @staticmethod
    def get_title(html: str) -> str:
        return get_title(html)

    @staticmethod
    def set_title(html: str, text: str) -> str:
        return set_title(html, text)

    # Description (legacy + meta)
    @staticmethod
    def get_description(html: str) -> str:
        return get_meta_description(html)

    @staticmethod
    def set_description(html: str, content: str) -> str:
        return set_meta_description(html, content)

    @staticmethod
    def get_meta_description(html: str) -> str:
        return get_meta_description(html)

    @staticmethod
    def set_meta_description(html: str, content: str) -> str:
        return set_meta_description(html, content)

    # Keywords (legacy + meta)
    @staticmethod
    def get_keywords(html: str) -> str:
        return get_meta_keywords(html)

    @staticmethod
    def set_keywords(html: str, content: str) -> str:
        return set_meta_keywords(html, content)

    @staticmethod
    def get_meta_keywords(html: str) -> str:
        return get_meta_keywords(html)

    @staticmethod
    def set_meta_keywords(html: str, content: str) -> str:
        return set_meta_keywords(html, content)

    # Sections
    @staticmethod
    def get_section(html: str, section_id: str) -> str:
        return get_section(html, section_id)

    @staticmethod
    def set_section(html: str, section_id: str, body_html: str) -> str:
        return set_section(html, section_id, body_html)

    @staticmethod
    def ensure_section(html: str, section_id: str) -> str:
        return ensure_section(html, section_id)

    @staticmethod
    def apply_sections(html: str, updates: Dict[str, str]) -> str:
        return apply_sections(html, updates)

    # Images
    @staticmethod
    def get_image_src(html: str, img_id: str) -> str:
        return get_image_src(html, img_id)

    @staticmethod
    def set_image_src(html: str, img_id: str, src: str, alt: Optional[str] = None) -> str:
        return set_image_src(html, img_id, src, alt)

    @staticmethod
    def get_image_alt(html: str, img_id: str) -> str:
        return get_image_alt(html, img_id)

    @staticmethod
    def set_image_alt(html: str, img_id: str, alt: str) -> str:
        return set_image_alt(html, img_id, alt)

    # Collection helpers
    @staticmethod
    def replace_main_inner(html: str, inner_html: str) -> str:
        return replace_main_inner(html, inner_html)

    @staticmethod
    def render_collection_main(title_h1: str, rows: list[dict]) -> str:
        return render_collection_main(title_h1, rows)

    # Head updates
    @staticmethod
    def update_head(
        html: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        keywords: Optional[str] = None,
    ) -> str:
        return update_head(html, title=title, description=description, keywords=keywords)
