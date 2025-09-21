# minipcb_catalog/models/index_model.py
"""
Index model for miniPCB Catalog — stores scan results for the Explorer.

- IndexItem: one HTML page with derived PN/Rev/Title/Status
- IndexModel: a simple container with helpers for filtering/grouping
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Iterable


@dataclass(slots=True)
class IndexItem:
    path: Path               # absolute path to the HTML file
    relpath: str             # path relative to project root (for display)
    pn: str                  # e.g., "04B-005"
    rev: str                 # e.g., "A1-01"
    title: str               # from <title> or H1 fallback
    status: str              # innerText of <span class="status-tag">, if present


@dataclass(slots=True)
class IndexModel:
    items: List[IndexItem] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.items)

    def filter(self, text: str) -> "IndexModel":
        t = text.lower().strip()
        if not t:
            return IndexModel(self.items.copy())
        out = [it for it in self.items
               if t in it.pn.lower()
               or t in it.rev.lower()
               or t in it.title.lower()
               or t in it.status.lower()
               or t in it.relpath.lower()]
        return IndexModel(out)

    def group_by_pn(self) -> Dict[str, List[IndexItem]]:
        g: Dict[str, List[IndexItem]] = {}
        for it in self.items:
            g.setdefault(it.pn, []).append(it)
        for v in g.values():
            v.sort(key=lambda x: x.rev)
        return g

    def add(self, item: IndexItem) -> None:
        self.items.append(item)

    def extend(self, items: Iterable[IndexItem]) -> None:
        self.items.extend(items)

    def sort(self) -> None:
        self.items.sort(key=lambda it: (it.pn, it.rev))
