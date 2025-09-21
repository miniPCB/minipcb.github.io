# minipcb_catalog/utils/html.py
from __future__ import annotations

import re
from typing import Tuple, List

# -------------------------------
# Generic helpers (string-based)
# -------------------------------

def _strip_tags(html: str) -> str:
    if not html:
        return ""
    # Remove tags, collapse whitespace
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# -------------------------------
# Comment-bounded blocks
# -------------------------------

def get_block_inner(page_html: str, begin_marker: str, end_marker: str, default_inner: str = "") -> str:
    if not page_html:
        return default_inner
    rx = re.compile(
        re.escape(begin_marker) + r"(.*?)" + re.escape(end_marker),
        re.I | re.S
    )
    m = rx.search(page_html)
    if not m:
        return default_inner
    return m.group(1)


def set_block_inner(page_html: str, begin_marker: str, end_marker: str, new_inner: str, default_inner: str = "") -> str:
    html = page_html or ""
    rx = re.compile(
        re.escape(begin_marker) + r"(.*?)" + re.escape(end_marker),
        re.I | re.S
    )
    if rx.search(html):
        return rx.sub(begin_marker + (new_inner or "") + end_marker, html, count=1)
    # If missing, create the block by appending near </main> or at end
    block = begin_marker + (new_inner or default_inner or "") + end_marker
    if "</main>" in html:
        return html.replace("</main>", block + "</main>", 1)
    if "</body>" in html:
        return html.replace("</body>", block + "</body>", 1)
    return html + block


def ensure_block(page_html: str, begin_marker: str, end_marker: str, default_inner: str = "") -> str:
    html = page_html or ""
    rx = re.compile(
        re.escape(begin_marker) + r"(.*?)" + re.escape(end_marker),
        re.I | re.S
    )
    if rx.search(html):
        return html
    block = begin_marker + (default_inner or "") + end_marker
    if "</main>" in html:
        return html.replace("</main>", block + "</main>", 1)
    if "</body>" in html:
        return html.replace("</body>", block + "</body>", 1)
    return html + block


# -------------------------------
# Metadata helpers
# -------------------------------

_TITLE_RX = re.compile(r"(<title[^>]*>)(.*?)(</title>)", re.I | re.S)
_HEAD_RX = re.compile(r"</head\s*>", re.I)

def get_title(page_html: str) -> str:
    m = _TITLE_RX.search(page_html or "")
    if not m:
        return ""
    # Clean whitespace inside title
    return re.sub(r"\s+", " ", m.group(2)).strip()


def set_title(page_html: str, new_title: str) -> str:
    """
    Replaces the content of the existing <title>. If missing, inserts a single
    well-formed <title> before </head>. Avoids duplicate/garbled titles.
    """
    html = page_html or ""
    title_text = (new_title or "").strip()
    if not title_text:
        return html
    if _TITLE_RX.search(html):
        return _TITLE_RX.sub(rf"\1{re.escape(title_text)}\3", html, count=1)
    # Insert before </head> if possible
    if _HEAD_RX.search(html):
        return _HEAD_RX.sub(f"<title>{title_text}</title></head>", html, count=1)
    # Fallback: prepend at top
    return f"<title>{title_text}</title>\n" + html


def get_keywords(page_html: str) -> str:
    m = re.search(r'<meta\s+name=["\']keywords["\']\s+content=["\'](.*?)["\']', page_html or "", re.I | re.S)
    return (m.group(1).strip() if m else "")


def set_keywords(page_html: str, kw: str) -> str:
    html = page_html or ""
    # Only replace existing keywords meta; don't invent one (keeps author control)
    rx = re.compile(r'(<meta\s+name=["\']keywords["\']\s+content=["\'])(.*?)("["\'])', re.I | re.S)
    if rx.search(html):
        safe = (kw or "")
        return rx.sub(r"\1" + re.escape(safe) + r"\3", html, count=1)
    return html


# -------------------------------
# Header slogan (<p class="slogan">…</p>)
# -------------------------------

_SLOGAN_RX = re.compile(r'(<p[^>]*class=["\']slogan["\'][^>]*>)(.*?)(</p>)', re.I | re.S)
_HEADER_RX = re.compile(r'(<header[^>]*>)(.*?)</header>', re.I | re.S)

def get_status_tag(page_html: str) -> str:
    m = _SLOGAN_RX.search(page_html or "")
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(2)).strip()


def set_status_tag(page_html: str, txt: str) -> str:
    html = page_html or ""
    slogan = (txt or "").strip()
    if not slogan:
        return html
    if _SLOGAN_RX.search(html):
        return _SLOGAN_RX.sub(rf"\1{slogan}\3", html, count=1)
    # Insert inside <header> if present (after opening tag)
    mh = _HEADER_RX.search(html)
    if mh:
        head_open, inner = mh.group(1), mh.group(2)
        # Try to place after <h1> if present
        h1_rx = re.compile(r'(<h1[^>]*>.*?</h1>)', re.I | re.S)
        if h1_rx.search(inner):
            inner = h1_rx.sub(rf"\1<p class=\"slogan\">{slogan}</p>", inner, count=1)
        else:
            inner = f'<p class="slogan">{slogan}</p>' + inner
        before, after = html[:mh.start()], html[mh.end():]
        return before + head_open + inner + "</header>" + after
    # Else, do nothing (don’t invent a header wrapper)
    return html


# -------------------------------
# Image helpers by element id
# -------------------------------

def get_img_src_by_id(page_html: str, elem_id: str) -> str:
    rx = re.compile(rf'<img[^>]+id=["\']{re.escape(elem_id)}["\'][^>]*>', re.I)
    m = rx.search(page_html or "")
    if not m:
        return ""
    tag = m.group(0)
    ms = re.search(r'src=["\']([^"\']+)["\']', tag, re.I)
    return ms.group(1).strip() if ms else ""


def set_img_src_by_id(page_html: str, elem_id: str, new_src: str) -> str:
    html = page_html or ""
    rx = re.compile(rf'(<img[^>]+id=["\']{re.escape(elem_id)}["\'][^>]*?)\s*(src=["\'][^"\']*["\'])?([^>]*>)', re.I | re.S)
    m = rx.search(html)
    if not m:
        return html
    before, _maybe_src, after = m.group(1), m.group(2), m.group(3)
    if _maybe_src:
        tag_new = re.sub(r'src=["\'][^"\']*["\']', f'src="{new_src}"', m.group(0), count=1, flags=re.I)
    else:
        tag_new = before + f' src="{new_src}"' + after
    return html[:m.start()] + tag_new + html[m.end():]


# -------------------------------
# Collection: extract first <table> in <main>
# -------------------------------

def _find_main(html: str) -> str:
    m = re.search(r'<main[^>]*>(.*)</main>', html or "", re.I | re.S)
    return m.group(1) if m else (html or "")


def extract_main_table(page_html: str) -> Tuple[List[str], List[List[str]]]:
    """
    Returns (headers, rows) for the first table inside <main>.
    Best-effort, tag-based; not a strict HTML parser.
    """
    main = _find_main(page_html or "")
    mt = re.search(r'<table[^>]*>(.*?)</table>', main, re.I | re.S)
    if not mt:
        return [], []
    table = mt.group(1)

    # Headers
    headers: List[str] = []
    thead = re.search(r'<thead[^>]*>(.*?)</thead>', table, re.I | re.S)
    if thead:
        # all <th> inside thead
        headers = [_strip_tags(th) for th in re.findall(r'<th[^>]*>(.*?)</th>', thead.group(1), re.I | re.S)]
    else:
        # Try first row's th/td
        first_row = re.search(r'<tr[^>]*>(.*?)</tr>', table, re.I | re.S)
        if first_row:
            headers = [_strip_tags(x) for x in re.findall(r'<th[^>]*>(.*?)</th>', first_row.group(1), re.I | re.S)]
            if not headers:
                headers = [_strip_tags(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', first_row.group(1), re.I | re.S)]

    # Body rows
    rows: List[List[str]] = []
    tbody = re.search(r'<tbody[^>]*>(.*?)</tbody>', table, re.I | re.S)
    body = tbody.group(1) if tbody else table
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', body, re.I | re.S):
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.I | re.S)
        rows.append([_strip_tags(c) for c in cells])

    return headers, rows
