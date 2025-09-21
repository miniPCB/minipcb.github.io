# minipcb_catalog/utils/images.py
"""
Image path helpers for miniPCB Catalog.

- Guess schematic/layout image filenames from page filename
- Validate existence
- Compute relative paths from page to image so preview matches website
"""

from __future__ import annotations

from pathlib import Path


def guess_schematic_for(page_path: Path, images_root: Path) -> Path:
    """
    Heuristic: <PN>_<REV>_schematic.(png|svg) under images_root
    """
    stem = page_path.stem  # e.g., "04B-005_A1-01"
    for ext in (".png", ".svg", ".jpg", ".jpeg"):
        p = images_root / f"{stem}_schematic{ext}"
        if p.exists():
            return p
    return images_root / f"{stem}_schematic.png"

def guess_layout_for(page_path: Path, images_root: Path) -> Path:
    """
    Heuristic: <PN>_<REV>_layout.(png|svg) under images_root
    """
    stem = page_path.stem
    for ext in (".png", ".svg", ".jpg", ".jpeg"):
        p = images_root / f"{stem}_layout{ext}"
        if p.exists():
            return p
    return images_root / f"{stem}_layout.png"

def rel_from_page(page_path: Path, target: Path) -> str:
    """
    Return a POSIX-style relative path from page to target (for HTML src=).
    """
    try:
        rel = target.resolve().relative_to(page_path.parent.resolve())
    except Exception:
        rel = target.resolve()
    # convert to POSIX separators for HTML
    return rel.as_posix()

def validate_image(path: Path) -> bool:
    return path.exists() and path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".gif"}
