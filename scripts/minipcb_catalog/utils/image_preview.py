from __future__ import annotations
from pathlib import Path

def resolve_image_path(mw, p: str) -> str:
    p = (p or "").strip()
    if not p:
        return ""
    if mw.current_path and not Path(p).is_absolute():
        return str((mw.current_path.parent / p).resolve())
    return p

def maybe_refresh_image_preview(mw, name: str) -> None:
    if name == "Schematic":
        mw.sch_preview.set_image_path(resolve_image_path(mw, mw.sch_src.text()))
    elif name == "Layout":
        mw.lay_preview.set_image_path(resolve_image_path(mw, mw.lay_src.text()))
