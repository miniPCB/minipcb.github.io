# minipcb_catalog/services/image_service.py
"""
ImageService — set/get schematic/layout image references in a page and
normalize paths to be relative to the page.

Integrates utils.images with the HTMLService.
"""

from __future__ import annotations

from pathlib import Path

from ..app import AppContext
from ..utils import images as IMG
from .html_service import HTMLService


class ImageService:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.html = HTMLService()

    def get_images(self, page_path: Path, html_text: str) -> dict:
        return {
            "schematic": self.html.get_image_src(html_text, "schematic_img"),
            "layout":    self.html.get_image_src(html_text, "layout_img"),
        }

    def set_image(self, page_path: Path, html_text: str, kind: str, image_file: Path) -> str:
        """
        kind: "schematic" or "layout"
        image_file: absolute path to selected image
        """
        if not IMG.validate_image(image_file):
            self.ctx.logger.warning("Invalid image file: %s", image_file)
        # Always store as path relative to the page
        rel = IMG.rel_from_page(page_path, image_file)
        key = "schematic_img" if kind == "schematic" else "layout_img"
        return self.html.set_image_src(html_text, key, rel)

    def guess_and_set_defaults(self, page_path: Path, html_text: str) -> str:
        """
        If schematic/layout are missing, try to guess likely files and set them.
        """
        current = self.get_images(page_path, html_text)
        updated = html_text
        if not current.get("schematic"):
            guess = IMG.guess_schematic_for(page_path, self.ctx.images_root)
            if guess.exists():
                updated = self.set_image(page_path, updated, "schematic", guess)
        if not current.get("layout"):
            guess = IMG.guess_layout_for(page_path, self.ctx.images_root)
            if guess.exists():
                updated = self.set_image(page_path, updated, "layout", guess)
        return updated
