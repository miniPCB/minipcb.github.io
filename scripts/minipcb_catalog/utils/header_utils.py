from __future__ import annotations

import re

# -------- <h1> (in header or anywhere) --------

_H1_IN_HEADER_RX = re.compile(
    r'(<header[^>]*>\s*<h1[^>]*>)(.*?)(</h1>)',
    re.I | re.S,
)
_H1_ANYWHERE_RX = re.compile(
    r'(<h1[^>]*>)(.*?)(</h1>)',
    re.I | re.S,
)

def extract_h1(html: str) -> str:
    m = _H1_IN_HEADER_RX.search(html or "")
    if m:
        return re.sub(r"\s+", " ", m.group(2)).strip()
    m = _H1_ANYWHERE_RX.search(html or "")
    return re.sub(r"\s+", " ", m.group(2)).strip() if m else ""

def set_h1(html: str, text: str) -> str:
    def repl_in_header(m):
        return m.group(1) + text + m.group(3)
    def repl_any(m):
        return m.group(1) + text + m.group(3)

    if _H1_IN_HEADER_RX.search(html or ""):
        return _H1_IN_HEADER_RX.sub(repl_in_header, html, count=1)
    if _H1_ANYWHERE_RX.search(html or ""):
        return _H1_ANYWHERE_RX.sub(repl_any, html, count=1)
    return html or ""


# -------- slogan <p class="slogan"> --------

_SLOGAN_RX = re.compile(
    r'(<p[^>]*\bclass=["\']slogan["\'][^>]*>)(.*?)(</p>)',
    re.I | re.S,
)

def extract_slogan(html: str) -> str:
    m = _SLOGAN_RX.search(html or "")
    return re.sub(r"\s+", " ", m.group(2)).strip() if m else ""

def set_slogan(html: str, text: str) -> str:
    def repl(m):
        return m.group(1) + text + m.group(3)
    if _SLOGAN_RX.search(html or ""):
        return _SLOGAN_RX.sub(repl, html, count=1)
    return html or ""


# -------- <title> (multi-line safe) --------

_TITLE_RX = re.compile(
    r'(<title[^>]*>)(.*?)(</title>)',
    re.I | re.S,
)

def extract_title(html: str) -> str:
    m = _TITLE_RX.search(html or "")
    if not m:
        return ""
    return re.sub(r"\s+", " ", (m.group(2) or "")).strip()

def set_title(html: str, text: str) -> str:
    def repl(m):
        return m.group(1) + (text or "") + m.group(3)

    if _TITLE_RX.search(html or ""):
        return _TITLE_RX.sub(repl, html, count=1)

    head_open = re.search(r'(<head[^>]*>)', html or "", re.I)
    if head_open:
        end = head_open.end(1)
        return (html or "")[:end] + f"<title>{text or ''}</title>" + (html or "")[end:]
    return html or ""
