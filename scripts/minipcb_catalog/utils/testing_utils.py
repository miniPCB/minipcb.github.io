from __future__ import annotations
import re

def set_testing_from_html(mw, testing_html: str) -> None:
    dtp_out = ""; atp_out = ""
    blocks = re.split(r'(<h3[^>]*>.*?</h3>)', testing_html or "", flags=re.I | re.S)
    if len(blocks) <= 1:
        dtp_out = testing_html or ""
    else:
        current = None
        for chunk in blocks:
            if re.search(r'Developmental\s+Test\s+Plan', chunk or "", re.I):
                current = "dtp"; continue
            if re.search(r'Automated\s+Test\s+Plan', chunk or "", re.I):
                current = "atp"; continue
            if current == "dtp": dtp_out += chunk
            elif current == "atp": atp_out += chunk
    mw.txt_dtp_out.setHtml((dtp_out or "").strip())
    mw.txt_atp_out.setHtml((atp_out or "").strip())

def compose_testing_html(mw) -> str:
    dtp_html = mw.txt_dtp_out.toHtml().strip()
    atp_html = mw.txt_atp_out.toHtml().strip()
    parts = []
    if dtp_html:
        parts.append('<h3>Developmental Test Plan (DTP)</h3>')
        parts.append(dtp_html)
    if atp_html:
        parts.append('<h3>Automated Test Plan (ATP)</h3>')
        parts.append(atp_html)
    return "\n".join(parts)
