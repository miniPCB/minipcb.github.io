from __future__ import annotations
import re

def extract_h1(html: str) -> str:
    m = re.search(r'<header[^>]*>\s*<h1[^>]*>(.*?)</h1>', html or "", re.I | re.S)
    if m:
        return re.sub(r'\s+', ' ', m.group(1)).strip()
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html or "", re.I | re.S)
    return re.sub(r'\s+', ' ', m.group(1)).strip() if m else ""

def extract_slogan(html: str) -> str:
    m = re.search(r'<p[^>]*class=["\']slogan["\'][^>]*>(.*?)</p>', html or "", re.I | re.S)
    import re as _re
    return _re.sub(r'\s+', ' ', m.group(1)).strip() if m else ""

def set_h1(html: str, text: str) -> str:
    def repl(m): return m.group(1) + text + m.group(3)
    if re.search(r'(<header[^>]*>\s*<h1[^>]*>)(.*?)(</h1>)', html or "", re.I | re.S):
        return re.sub(r'(<header[^>]*>\s*<h1[^>]*>)(.*?)(</h1>)', repl, html, count=1, flags=re.I | re.S)
    if re.search(r'(<h1[^>]*>)(.*?)(</h1>)', html or "", re.I | re.S):
        return re.sub(r'(<h1[^>]*>)(.*?)(</h1>)', repl, html, count=1, flags=re.I | re.S)
    return html or ""

def set_slogan(html: str, text: str) -> str:
    def repl(m): return m.group(1) + text + m.group(3)
    if re.search(r'(<p[^>]*class=["\']slogan["\'][^>]*>)(.*?)(</p>)', html or "", re.I | re.S):
        return re.sub(r'(<p[^>]*class=["\']slogan["\'][^>]*>)(.*?)(</p>)', repl, html, count=1, flags=re.I | re.S)
    return html or ""
