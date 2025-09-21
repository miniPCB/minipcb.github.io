from __future__ import annotations
import re
from PyQt5.QtWidgets import QTableWidgetItem, QTableWidget

_IMG_SRC_RX = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
_IMG_ALT_RX = re.compile(r'alt=["\']([^"\']*)["\']', re.I)
_IFRAME_SRC_RX = re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.I)

def set_details_from_html(mw, html_fragment: str) -> None:
    def _grab(label):
        m = re.search(rf"<strong>\s*{re.escape(label)}\s*:\s*</strong>\s*([^<]+)", html_fragment or "", re.I)
        return (m.group(1).strip() if m else "")
    mw.det_part.setText(_grab("Part No"))
    mw.det_title.setText(_grab("Title"))
    mw.det_board.setText(_grab("Board Size"))
    mw.det_pieces.setText(_grab("Pieces per Panel"))
    mw.det_panel.setText(_grab("Panel Size"))

def set_videos_from_html(mw, html_fragment: str) -> None:
    mw.tbl_videos.setRowCount(0)
    for m in _IFRAME_SRC_RX.finditer(html_fragment or ""):
        r = mw.tbl_videos.rowCount()
        mw.tbl_videos.insertRow(r)
        mw.tbl_videos.setItem(r, 0, QTableWidgetItem(m.group(1)))

def set_resources_from_html(mw, html_fragment: str) -> None:
    mw.tbl_resources.setRowCount(0)
    for m in _IFRAME_SRC_RX.finditer(html_fragment or ""):
        r = mw.tbl_resources.rowCount()
        mw.tbl_resources.insertRow(r)
        mw.tbl_resources.setItem(r, 0, QTableWidgetItem(m.group(1)))

def set_downloads_from_html(mw, html_fragment: str) -> None:
    mw.tbl_downloads.setRowCount(0)
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_fragment or "", re.I | re.S):
        href, text = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
        r = mw.tbl_downloads.rowCount()
        mw.tbl_downloads.insertRow(r)
        mw.tbl_downloads.setItem(r, 0, QTableWidgetItem(text or href))
        mw.tbl_downloads.setItem(r, 1, QTableWidgetItem(href))

def set_image_fields_from_html(mw, section_html: str, which: str) -> None:
    src = ""; alt = ""
    m = _IMG_SRC_RX.search(section_html or "")
    if m: src = m.group(1).strip()
    m = _IMG_ALT_RX.search(section_html or "")
    if m: alt = m.group(1).strip()
    if which == "schematic":
        mw.sch_src.setText(src); mw.sch_alt.setText(alt)
    else:
        mw.lay_src.setText(src); mw.lay_alt.setText(alt)

def compose_details_html(mw) -> str:
    def row(label, val): return f'<p><strong>{label}:</strong> {val}</p>' if val else ""
    return "".join([
        row("Part No", mw.det_part.text().strip()),
        row("Title", mw.det_title.text().strip()),
        row("Board Size", mw.det_board.text().strip()),
        row("Pieces per Panel", mw.det_pieces.text().strip()),
        row("Panel Size", mw.det_panel.text().strip()),
    ])

def compose_iframe_list_html(tbl: QTableWidget) -> str:
    out = []
    for r in range(tbl.rowCount()):
        url = tbl.item(r, 0).text().strip() if tbl.item(r, 0) else ""
        if not url: continue
        out.append(f'<iframe src="{url}" loading="lazy" allowfullscreen></iframe>')
    return "\n".join(out)

def compose_downloads_html(tbl: QTableWidget) -> str:
    items = []
    for r in range(tbl.rowCount()):
        text = tbl.item(r, 0).text().strip() if tbl.item(r, 0) else ""
        href = tbl.item(r, 1).text().strip() if tbl.item(r, 1) else ""
        if not (text or href): continue
        a = f'<a href="{href or "#"}">{text or href or "Download"}</a>'
        items.append(f"<li>{a}</li>")
    return f"<ul>\n{''.join(items)}\n</ul>" if items else ""

def compose_img_block(src: str, alt: str) -> str:
    if not src:
        return ""
    return f'<div class="lightbox-container"><img src="{src}" loading="lazy" class="zoomable" alt="{alt}"></div>'
