# minipcb_catalog/ui/tabs/explorer_tab.py
"""
ExplorerTab — a list-based explorer for pages.

This widget is optional for the initial scaffold (MainWindow already
has a simple list). It’s provided for clean separation so MainWindow
can embed this later and listen to its signals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem

from ...services.index_service import IndexService
from ...app import AppContext
from ...models.index_model import IndexModel


class ExplorerTab(QWidget):
    pathActivated = pyqtSignal(str)   # emits absolute path string

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.index = IndexModel()

        self.search = QLineEdit(placeholderText="Filter by PN / Rev / Title / Status / Path…")
        self.listw = QListWidget()
        self.search.textChanged.connect(self._apply_filter)
        self.listw.itemActivated.connect(self._on_activate)

        lay = QVBoxLayout()
        lay.addWidget(self.search)
        lay.addWidget(self.listw)
        self.setLayout(lay)

    def rescan(self):
        svc = IndexService(self.ctx)
        self.index = svc.build_index()
        self._populate(self.index)

    # ---- internals ----

    def _populate(self, model: IndexModel):
        self.listw.clear()
        for it in model.items:
            item = QListWidgetItem(f"{it.pn or '(no PN)'} {it.rev or ''} — {it.title}")
            item.setData(Qt.UserRole, str(it.path))
            item.setToolTip(it.relpath)
            self.listw.addItem(item)

    def _apply_filter(self, text: str):
        sub = self.index.filter(text)
        self._populate(sub)

    def _on_activate(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if path:
            self.pathActivated.emit(path)
