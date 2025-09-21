from __future__ import annotations
from typing import Optional, Tuple, Dict, List
from pathlib import Path
import re
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTextEdit, QDialogButtonBox,
                             QLineEdit, QFormLayout, QListWidget, QListWidgetItem, QHBoxLayout, QComboBox)
from ..app import AppContext

def open_seed_dialog(parent, title: str, initial: str) -> Optional[str]:
    dlg = QDialog(parent); dlg.setWindowTitle(title); dlg.resize(760, 540)
    v = QVBoxLayout(dlg)
    info = QLabel(f"Enter seed notes for {title}. Plain text only.")
    info.setWordWrap(True); v.addWidget(info)
    ed = QTextEdit(); ed.setAcceptRichText(False); ed.setPlainText(initial); ed.setMinimumHeight(380)
    v.addWidget(ed, 1)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, dlg)
    v.addWidget(btns)
    btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
    if dlg.exec_() == QDialog.Accepted:
        return ed.toPlainText().strip()
    return None

def open_testing_seeds_dialog(parent, dtp_init: str, atp_init: str) -> Optional[Tuple[str,str]]:
    dlg = QDialog(parent); dlg.setWindowTitle("Edit Testing Seeds"); dlg.resize(760, 560)
    v = QVBoxLayout(dlg)
    frm = QFormLayout()
    ed1 = QTextEdit(); ed1.setAcceptRichText(False); ed1.setPlainText(dtp_init); ed1.setMinimumHeight(200)
    ed2 = QTextEdit(); ed2.setAcceptRichText(False); ed2.setPlainText(atp_init); ed2.setMinimumHeight(200)
    frm.addRow("DTP Seed:", ed1); frm.addRow("ATP Seed:", ed2)
    v.addLayout(frm)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, dlg)
    v.addWidget(btns)
    btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
    if dlg.exec_() == QDialog.Accepted:
        return ed1.toPlainText().strip(), ed2.toPlainText().strip()
    return None

class NavLinkDialog(QDialog):
    def __init__(self, ctx: AppContext, current_page: Optional[Path], parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.current_page = current_page
        self.setWindowTitle("Add Navigation Link")
        self.resize(820, 600)

        v = QVBoxLayout(self)

        # Filters
        filt_row = QHBoxLayout()
        self.edt_search = QLineEdit(placeholderText="Search by filename or title…")
        self.cmb_ext = QComboBox(); self.cmb_ext.addItems(["All", "HTML", "Markdown"])
        filt_row.addWidget(QLabel("Filter:"))
        filt_row.addWidget(self.edt_search, 1)
        filt_row.addWidget(QLabel("Type:"))
        filt_row.addWidget(self.cmb_ext)
        v.addLayout(filt_row)

        self.lst = QListWidget(); v.addWidget(self.lst, 1)

        frm = QFormLayout()
        self.out_text = QLineEdit()
        self.out_href = QLineEdit()
        frm.addRow("Text:", self.out_text)
        frm.addRow("Href:", self.out_href)
        v.addLayout(frm)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        v.addWidget(btns)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)

        self._title_cache: Dict[Path, str] = {}
        self._title_rx = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)
        self._all_files: List[Path] = []
        for pat in ("*.html","*.htm","*.md","*.markdown"):
            self._all_files.extend(sorted(self.ctx.root.rglob(pat)))

        self.edt_search.textChanged.connect(self._apply_filter)
        self.cmb_ext.currentIndexChanged.connect(self._apply_filter)
        self.lst.currentItemChanged.connect(lambda *_: self._on_select())
        self._apply_filter()
        if self.lst.count() > 0: self.lst.setCurrentRow(0)

    def _get_title(self, p: Path) -> str:
        if p in self._title_cache: return self._title_cache[p]
        t = ""
        try:
            if p.suffix.lower() in {".html",".htm"}:
                txt = p.read_text("utf-8", errors="ignore")
                m = self._title_rx.search(txt)
                if m:
                    import re as _re
                    t = _re.sub(r"\s+", " ", m.group(1)).strip()
        except Exception:
            t = ""
        self._title_cache[p] = t
        return t

    def _ext_ok(self, p: Path) -> bool:
        sel = self.cmb_ext.currentText()
        if sel == "All": return True
        if sel == "HTML": return p.suffix.lower() in {".html",".htm"}
        if sel == "Markdown": return p.suffix.lower() in {".md",".markdown"}
        return True

    def _score(self, p: Path) -> int:
        name = p.name.lower()
        if name == "index.html": return -100
        if "index" in name: return -50
        return 0

    def _apply_filter(self):
        self.lst.clear()
        q = self.edt_search.text().strip().lower()
        items = []
        for p in self._all_files:
            if not self._ext_ok(p): continue
            rel = p.relative_to(self.ctx.root)
            title = self._get_title(p)
            text = f"{rel.as_posix()} — {title}" if title else rel.as_posix()
            if q and q not in text.lower(): continue
            items.append((p, text))
        items.sort(key=lambda t: (self._score(t[0]), t[1].lower()))
        for p, text in items:
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, str(p))
            it.setToolTip(str(p.relative_to(self.ctx.root)))
            self.lst.addItem(it)

    def _on_select(self):
        it = self.lst.currentItem()
        if not it: return
        p = Path(it.data(Qt.UserRole))
        rel = p.relative_to(self.ctx.root)
        title = self._get_title(p)
        self.out_text.setText(title or p.stem)
        # build relative href from current_page
        try:
            base = (self.ctx.root / (self.current_page.relative_to(self.ctx.root).parent if self.current_page else Path(".")))
            rel_href = Path.relpath((self.ctx.root / rel), base)
            href = str(rel_href).replace("\\", "/")
        except Exception:
            href = rel.as_posix()
        self.out_href.setText(href)

    def run(self):
        if self.exec_() == QDialog.Accepted:
            text = self.out_text.text().strip()
            href = self.out_href.text().strip()
            if text or href:
                return text or href, href or "#"
        return None
