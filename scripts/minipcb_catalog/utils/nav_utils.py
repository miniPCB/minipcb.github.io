from __future__ import annotations

import re
from typing import List
from PyQt5.QtWidgets import QTableWidgetItem

# Match the nav <ul> block with class="nav-links"
_NAV_UL_RX = re.compile(
    r'(<ul[^>]*\bclass=["\']nav-links["\'][^>]*>)(?P<body>.*?)(</ul>)',
    re.I | re.S,
)

_A_HREF_RX = re.compile(
    r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.I | re.S,
)


def set_nav_from_html(mw, html: str) -> None:
    """Populate the navigation table from the HTML's nav <ul> block."""
    mw.tbl_nav.setRowCount(0)
    m = _NAV_UL_RX.search(html or "")
    if not m:
        return
    body = m.group("body")
    for a in _A_HREF_RX.finditer(body or ""):
        href = (a.group(1) or "").strip()
        text = re.sub(r"\s+", " ", (a.group(2) or "")).strip()
        r = mw.tbl_nav.rowCount()
        mw.tbl_nav.insertRow(r)
        mw.tbl_nav.setItem(r, 0, QTableWidgetItem(text or href or "Link"))
        mw.tbl_nav.setItem(r, 1, QTableWidgetItem(href or "#"))


def write_nav_to_html(mw, html: str) -> str:
    """Write the navigation table back into the first nav <ul class="nav-links"> in the HTML.

    If the UL doesn't exist:
      - If there's a </nav>, insert the <ul> just before it.
      - Else if there's a <body>, insert <nav><ul>…</ul></nav> right after <body>.
      - Otherwise, return the HTML unchanged (fail safe).
    """
    items: List[str] = []
    for r in range(mw.tbl_nav.rowCount()):
        text = mw.tbl_nav.item(r, 0).text().strip() if mw.tbl_nav.item(r, 0) else ""
        href = mw.tbl_nav.item(r, 1).text().strip() if mw.tbl_nav.item(r, 1) else ""
        if not (text or href):
            continue
        items.append(f'<li><a href="{href or "#"}">{text or href or "Link"}</a></li>')

    new_body = "".join(items)

    def _repl_ul(m):
        # Preserve the original <ul ...> and </ul>, replace only its body.
        return m.group(1) + new_body + m.group(3)

    if _NAV_UL_RX.search(html or ""):
        # Replace body within the existing UL (first occurrence only)
        return _NAV_UL_RX.sub(_repl_ul, html, count=1)

    # No existing UL — build one
    ul_block = f'<ul class="nav-links">{new_body}</ul>'

    # If there's a closing </nav>, put UL right before it
    if "</nav>" in (html or ""):
        return (html or "").replace("</nav>", ul_block + "</nav>", 1)

    # Else, insert a minimal <nav> with the UL right after <body ...>
    # IMPORTANT: use a single backreference \1 (NOT \\1)
    if re.search(r'(<body[^>]*>)', html or "", re.I):
        return re.sub(
            r'(<body[^>]*>)',
            lambda m: m.group(1) + "<nav>" + ul_block + "</nav>",
            html or "",
            count=1,
            flags=re.I,
        )

    # No body/nav found — leave HTML as-is (fail safe)
    return html or ""


def nav_del_row(mw) -> None:
    r = mw.tbl_nav.currentRow()
    if r >= 0:
        mw.tbl_nav.removeRow(r)


def move_row(tbl, delta: int) -> None:
    r = tbl.currentRow()
    if r < 0:
        return
    nr = max(0, min(r + delta, tbl.rowCount() - 1))
    if nr == r:
        return

    # Insert new row at destination and move items
    tbl.insertRow(nr)
    from PyQt5.QtWidgets import QTableWidgetItem

    src = r + (1 if nr < r else 0)
    for c in range(tbl.columnCount()):
        it = tbl.takeItem(src, c)
        if it is None:
            it = QTableWidgetItem("")
        tbl.setItem(nr, c, it)
    tbl.removeRow(src)
    tbl.setCurrentCell(nr, 0)
