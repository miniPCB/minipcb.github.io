# minipcb_catalog/services/index_service.py
"""
IndexService — scans the project root for HTML pages and derives PN/Rev/Title/Status.

Filename conventions supported (tweak as needed):
  "<PN>_<REV>.html"  e.g., 04B-005_A1-01.html
  "<PN>-<REV>.html"  e.g., 04B-005-A1-01.html
If parsing fails, PN/Rev fall back to "" and "".

Title and status are read from the document DOM using lightweight regex.
"""

from __future__ import annotations

from pathlib import Path
import re
import fnmatch
from typing import List

from ..app import AppContext
from .. import constants
from ..models.index_model import IndexModel, IndexItem

TITLE_RX = re.compile(r"<\s*title[^>]*>(.*?)</\s*title\s*>", re.IGNORECASE | re.DOTALL)
STATUS_RX = re.compile(
    r'<\s*span[^>]*class=["\']status-tag["\'][^>]*>(.*?)</\s*span\s*>',
    re.IGNORECASE | re.DOTALL,
)

PN_REV_UNDERSCORE = re.compile(r"(?P<pn>\d{2}[A-Z]-\d{3})_(?P<rev>[A-Za-z0-9-]+)\.html?$")
PN_REV_DASH      = re.compile(r"(?P<pn>\d{2}[A-Z]-\d{3})-(?P<rev>[A-Za-z0-9-]+)\.html?$")


class IndexService:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx

    def build_index(self) -> IndexModel:
        root = self.ctx.root.resolve()
        paths: List[Path] = []

        # Recursive scan using the globs from constants (respect ignore globs)
        for g in constants.HTML_GLOBS:
            for p in root.rglob(g.replace("**/", "")):
                if self._is_ignored(p, root):
                    continue
                if p.suffix.lower() not in {".html", ".htm"}:
                    continue
                paths.append(p)

        items: List[IndexItem] = []
        for p in sorted(set(paths)):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            title = self._extract(TITLE_RX, text) or p.stem
            status = self._extract(STATUS_RX, text)
            pn, rev = self._pn_rev_from_name(p.name)
            rel = str(p.resolve().relative_to(root))
            items.append(IndexItem(
                path=p.resolve(),
                relpath=rel,
                pn=pn,
                rev=rev,
                title=title,
                status=status or "",
            ))
        model = IndexModel(items)
        model.sort()
        return model

    # ---- internals ----

    def _is_ignored(self, p: Path, root: Path) -> bool:
        rel = str(p.resolve().relative_to(root))
        for pat in constants.IGNORE_GLOBS:
            # adapt "**/x/**" style to fnmatch against posix path
            if fnmatch.fnmatch(rel.replace("\\", "/"), pat.replace("**/", "").replace("**", "*")):
                return True
        return False

    def _extract(self, rx: re.Pattern[str], text: str) -> str:
        m = rx.search(text)
        return (m.group(1).strip() if m else "").strip()

    def _pn_rev_from_name(self, name: str) -> tuple[str, str]:
        m = PN_REV_UNDERSCORE.match(name)
        if m:
            return m.group("pn"), m.group("rev")
        m = PN_REV_DASH.match(name)
        if m:
            return m.group("pn"), m.group("rev")
        return "", ""
