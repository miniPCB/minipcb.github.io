from __future__ import annotations
import re
from typing import List
from PyQt5.QtWidgets import QTableWidgetItem

_NAV_UL_RX = re.compile(r'(<ul[^>]*class=["\']nav-links["\'][^>]*>)(?P<body>.*?)(</ul>)', re.I | re.S)

def set_nav_from_html(mw, html: str) -> None:
    mw.tbl_nav.setRowCount(0)
    m = _NAV_UL_RX.search(html or "")
    if not m:
        return
    body = m.group("body")
    for a in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', body, re.I | re.S):
        href = a.group(1).strip()
        text = re.sub(r"\s+", " ", a.group(2)).strip()
        r = mw.tbl_nav.rowCount()
        mw.tbl_nav.insertRow(r)
        mw.tbl_nav.setItem(r, 0, QTableWidgetItem(text or href))
        mw.tbl_nav.setItem(r, 1, QTableWidgetItem(href or "#"))

def write_nav_to_html(mw, html: str) -> str:
    items: List[str] = []
    for r in range(mw.tbl_nav.rowCount()):
        text = mw.tbl_nav.item(r, 0).text().strip() if mw.tbl_nav.item(r, 0) else ""
        href = mw.tbl_nav.item(r, 1).text().strip() if mw.tbl_nav.item(r, 1) else ""
        if not (text or href):
            continue
        items.append(f'<li><a href="{href or "#"}">{text or href or "Link"}</a></li>')
    new_body = "".join(items) if items else ""
    def repl(m): return m.group(1) + new_body + m.group(3)
    if _NAV_UL_RX.search(html or ""):
        return _NAV_UL_RX.sub(repl, html, count=1)
    ul_block = f'<ul class="nav-links">{new_body}</ul>'
    if "</nav>" in (html or ""):
        return (html or "").replace("</nav>", ul_block + "</nav>", 1)
    if "<body" in (html or ""):
        return re.sub(r'(<body[^>]*>)', r'\1<nav>' + ul_block + '</nav>', html or "", count=1, flags=re.I)
    return html or ""

def nav_del_row(mw) -> None:
    r = mw.tbl_nav.currentRow()
    if r >= 0:
        mw.tbl_nav.removeRow(r)

def move_row(tbl, delta: int) -> None:
    r = tbl.currentRow()
    if r < 0:
        return
    nr = max(0, min(r + delta, tbl.rowCount()-1))
    if nr == r:
        return
    tbl.insertRow(nr)
    from PyQt5.QtWidgets import QTableWidgetItem
    for c in range(tbl.columnCount()):
        it = tbl.takeItem(r + (1 if nr < r else 0), c)
        if it is None:
            it = QTableWidgetItem("")
        tbl.setItem(nr, c, it)
    tbl.removeRow(r + (1 if nr < r else 0))
    tbl.setCurrentCell(nr, 0)
