# minipcb_catalog/utils/html.py
"""
Lightweight HTML helpers for miniPCB Catalog.

String-based (regex) utilities to:
- Read/write HTML text
- Find/ensure/set comment-bounded section blocks
- Get/set <title>, <meta name="keywords">, and a <span class="status-tag">
- Get/set <img id="..."> src attributes

These mirror the ad-hoc helpers used early in MainWindow so we can later
refactor the UI to import from here (single source of truth).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
import re

# ------------------------- file I/O -----------------------------------------

def read_html_text(path: Path, encoding: str = "utf-8") -> str:
    return path.read_text(encoding=encoding)

def write_html_text(path: Path, html: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding=encoding)

# ------------------------- block helpers ------------------------------------

def find_block(html: str, begin: str, end: str) -> Optional[Tuple[int, int, int, int]]:
    """
    Return (b0, b1, e0, e1) indices around a comment-bounded block, or None.

    b0 .. b1  => the BEGIN marker [exclusive of content]
    e0 .. e1  => the END marker   [exclusive of content]
    """
    b0 = html.find(begin)
    if b0 < 0:
        return None
    b1 = b0 + len(begin)
    e0 = html.find(end, b1)
    if e0 < 0:
        return None
    e1 = e0 + len(end)
    return (b0, b1, e0, e1)

def get_block_inner(html: str, begin: str, end: str, default: str = "") -> str:
    loc = find_block(html, begin, end)
    if not loc:
        return default
    b0, b1, e0, _ = loc
    return html[b1:e0]

def ensure_block(html: str, begin: str, end: str, default_inner: str = "") -> str:
    """
    Ensure a comment-bounded block exists. If missing, insert before </body>,
    otherwise append to end of document.
    """
    if find_block(html, begin, end):
        return html
    insertion = f"\n{begin}\n{default_inner}\n{end}\n"
    m = re.search(r"</\s*body\s*>", html, flags=re.IGNORECASE)
    if m:
        return html[:m.start()] + insertion + html[m.start():]
    return html + insertion

def set_block_inner(html: str, begin: str, end: str, new_inner: str, default_inner: str = "") -> str:
    """
    Replace or create a comment-bounded block's inner HTML.
    """
    html = ensure_block(html, begin, end, default_inner=default_inner)
    b0, b1, e0, e1 = find_block(html, begin, end)  # type: ignore
    return html[:b1] + "\n" + new_inner.strip() + "\n" + html[e0:]

# ------------------------- metadata helpers ---------------------------------

_TITLE_RX = re.compile(r"(<\s*title\s*[^>]*>)(.*?)(</\s*title\s*>)",
                       re.IGNORECASE | re.DOTALL)

def get_title(html: str) -> str:
    m = _TITLE_RX.search(html)
    return m.group(2).strip() if m else ""

def set_title(html: str, new_title: str) -> str:
    if _TITLE_RX.search(html):
        return _TITLE_RX.sub(rf"\1{new_title}\3", html, count=1)
    # Insert into <head> if present; else prepend a minimal head
    m = re.search(r"<\s*head\s*[^>]*>", html, re.IGNORECASE)
    if m:
        ins = f"{m.group(0)}\n<title>{new_title}</title>"
        return html[:m.start()] + ins + html[m.end():]
    return f"<head><title>{new_title}</title></head>\n{html}"

_KEYWORDS_RX = re.compile(
    r'<\s*meta\s+name=["\']keywords["\']\s+content=["\'](.*?)["\']\s*/?>',
    re.IGNORECASE | re.DOTALL
)

def get_keywords(html: str) -> str:
    m = _KEYWORDS_RX.search(html)
    return m.group(1).strip() if m else ""

def set_keywords(html: str, kw: str) -> str:
    if _KEYWORDS_RX.search(html):
        return _KEYWORDS_RX.sub(lambda _: f'<meta name="keywords" content="{kw}">', html, count=1)
    # Insert before </head> if possible
    m = re.search(r"</\s*head\s*>", html, re.IGNORECASE)
    if m:
        return html[:m.start()] + f'\n<meta name="keywords" content="{kw}">\n' + html[m.start():]
    return f'<meta name="keywords" content="{kw}">\n{html}'

_STATUS_TAG_RX = re.compile(
    r'(<\s*span[^>]*class=["\']status-tag["\'][^>]*>)(.*?)(</\s*span\s*>)',
    re.IGNORECASE | re.DOTALL
)

def get_status_tag(html: str) -> str:
    m = _STATUS_TAG_RX.search(html)
    return m.group(2).strip() if m else ""

def set_status_tag(html: str, txt: str) -> str:
    if _STATUS_TAG_RX.search(html):
        return _STATUS_TAG_RX.sub(rf"\1{txt}\3", html, count=1)
    # If not present, insert near top of <body>
    m = re.search(r"<\s*body[^>]*>", html, re.IGNORECASE)
    chip = f'<span class="status-tag">{txt}</span>'
    if m:
        return html[:m.end()] + "\n" + chip + html[m.end():]
    return chip + "\n" + html

# ------------------------- image helpers ------------------------------------

def get_img_src_by_id(html: str, img_id: str) -> str:
    rx = re.compile(
        rf'<\s*img[^>]*\bid=["\']{re.escape(img_id)}["\'][^>]*\s+src=["\'](.*?)["\']',
        re.IGNORECASE | re.DOTALL
    )
    m = rx.search(html)
    return m.group(1).strip() if m else ""

def set_img_src_by_id(html: str, img_id: str, src: str) -> str:
    """
    Ensure <img id="..."> exists and set its src attribute.
    If missing, inject an <img> before </body> (or append to end).
    """
    rx = re.compile(
        rf'(<\s*img[^>]*\bid=["\']{re.escape(img_id)}["\'][^>]*)(>)',
        re.IGNORECASE | re.DOTALL
    )
    m = rx.search(html)
    if not m:
        tag = f'<img id="{img_id}" src="{src}">'
        end_body = re.search(r"</\s*body\s*>", html, re.IGNORECASE)
        if end_body:
            return html[:end_body.start()] + "\n" + tag + "\n" + html[end_body.start():]
        return html + "\n" + tag
    tag_open = m.group(1)
    # remove any existing src="" and append our src
    tag_open = re.sub(r'\s+src=["\'].*?["\']', "", tag_open)
    tag_open = tag_open.rstrip() + f' src="{src}"'
    return html[:m.start(1)] + tag_open + m.group(2) + html[m.end(2):]
