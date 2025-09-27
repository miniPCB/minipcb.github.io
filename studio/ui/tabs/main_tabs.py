
import re
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit, QListWidget,
    QPushButton, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QPlainTextEdit, QGroupBox, QComboBox
)
from PyQt5.QtCore import Qt
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    from PyQt5.QtCore import QUrl
except Exception:
    QWebEngineView = None
    QUrl = None

from bs4 import BeautifulSoup
from services.template_loader import Templates
from services.html_service import HtmlService

class MainTabs(QWidget):
    def __init__(self, ctx, get_editor_text_callable=None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.get_editor_text = get_editor_text_callable
        self.current_path = None
        self.templates = None
        self.htmlsvc = None

        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        self.tabs = QTabWidget(self)
        lay.addWidget(self.tabs)

    # ---------------------- Helpers ----------------------
    def _is_collection_file(self, path: Path) -> bool:
        # Collection = XX.html or XXX.html
        if path.suffix.lower() != ".html":
            return False
        stem = path.stem
        return len(stem) in (2, 3)

    def _is_board_file(self, path: Path) -> bool:
        # Board = XXX-XX.html or XXX-XXX.html
        # Enforce patterns with alnum codes separated by a single hyphen.
        if path.suffix.lower() != ".html":
            return False
        m = re.fullmatch(r"[A-Za-z0-9]{3}-[A-Za-z0-9]{2,3}", path.stem)
        return m is not None

    def _clear_tabs(self):
        while self.tabs.count():
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            w.deleteLater()

    # ---------------------- Public API ----------------------
    def load_html_file(self, path: Path):
        self.current_path = Path(path)
        html_text = ""
        try:
            if self.current_path.exists():
                html_text = self.current_path.read_text(encoding="utf-8")
        except Exception:
            pass

        # Build services
        try:
            self.templates = Templates(self.ctx.templates_dir)
            self.htmlsvc = HtmlService(self.templates)
            meta = self.htmlsvc.extract_metadata(html_text) if html_text else {}
        except Exception:
            meta = {}

        self._clear_tabs()

        if self._is_collection_file(self.current_path):
            self._build_collection_tabs()
            self._populate_collection(meta, html_text)
        elif self._is_board_file(self.current_path):
            self._build_board_tabs()
            self._populate_board(meta, html_text)
        else:
            # Fallback: just raw text
            self._build_raw_only()
            self.raw_text.setPlainText(html_text or "")

    # ---------------------- Collection Tabs ----------------------
    def _build_collection_tabs(self):
        # Collection Metadata
        meta_w = QWidget(); form = QFormLayout(meta_w)
        self.c_title = QLineEdit()
        self.c_slogan = QLineEdit()
        self.c_keywords = QLineEdit()
        self.c_description = QLineEdit()
        form.addRow("Title:", self.c_title)
        form.addRow("Slogan:", self.c_slogan)
        form.addRow("Keywords (CSV):", self.c_keywords)
        form.addRow("Description:", self.c_description)
        self.tabs.addTab(meta_w, "Metadata")

        # Links table
        links_w = QWidget(); v = QVBoxLayout(links_w)
        self.collection_table = QTableWidget(0, 2, self)
        self.collection_table.setHorizontalHeaderLabels(["Text", "URL"])
        self.collection_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        v.addWidget(self.collection_table)
        hb = QHBoxLayout()
        self.btn_col_add_above = QPushButton("Add Above")
        self.btn_col_add_below = QPushButton("Add Below")
        self.btn_col_del = QPushButton("Delete")
        hb.addWidget(self.btn_col_add_above); hb.addWidget(self.btn_col_add_below); hb.addWidget(self.btn_col_del)
        v.addLayout(hb)
        self.btn_col_add_above.clicked.connect(lambda: self._table_insert(self.collection_table, -1))
        self.btn_col_add_below.clicked.connect(lambda: self._table_insert(self.collection_table, +1))
        self.btn_col_del.clicked.connect(lambda: self._table_delete(self.collection_table))
        self.tabs.addTab(links_w, "Links")

        # Raw Text
        self._build_raw_text_tab()

    def _populate_collection(self, meta: dict, html_text: str):
        # Set simple SEO/title fields if present
        try:
            soup = BeautifulSoup(html_text or "", "html.parser")
            title = soup.title.get_text(strip=True) if soup.title else ""
            self.c_title.setText(title)
            # meta tags
            def m(name):
                tag = soup.find("meta", attrs={"name": name})
                return tag.get("content","") if tag else ""
            self.c_slogan.setText(m("slogan"))
            self.c_keywords.setText(m("keywords"))
            self.c_description.setText(m("description"))
            # links
            self.collection_table.setRowCount(0)
            links = soup.select("main a") or soup.find_all("a")
            for a in links:
                text = a.get_text(strip=True)
                href = a.get("href", "")
                r = self.collection_table.rowCount()
                self.collection_table.insertRow(r)
                self.collection_table.setItem(r, 0, QTableWidgetItem(text))
                self.collection_table.setItem(r, 1, QTableWidgetItem(href))
            # raw
            self.raw_text.setPlainText(html_text or "")
        except Exception:
            pass

    # ---------------------- Board Tabs ----------------------
    def _build_board_tabs(self):
        # Metadata
        self.meta_tab = QTabWidget(self)
        # Basics
        basics = QWidget(); form = QFormLayout(basics)
        self.in_pn = QLineEdit(); self.in_title = QLineEdit()
        self.in_board_size = QLineEdit(); self.in_pieces = QLineEdit(); self.in_panel_size = QLineEdit()
        form.addRow("PN:", self.in_pn)
        form.addRow("Title:", self.in_title)
        form.addRow("Board Size:", self.in_board_size)
        form.addRow("Pieces per Panel:", self.in_pieces)
        form.addRow("Panel Size:", self.in_panel_size)
        self.meta_tab.addTab(basics, "Basics")

        # SEO
        seo = QWidget(); sform = QFormLayout(seo)
        self.in_slogan = QLineEdit(); self.in_keywords = QLineEdit(); self.in_description = QLineEdit()
        sform.addRow("Slogan:", self.in_slogan)
        sform.addRow("Keywords (CSV):", self.in_keywords)
        sform.addRow("Description:", self.in_description)
        self.meta_tab.addTab(seo, "SEO")

        # Navigation
        navw = QWidget(); vbox = QVBoxLayout(navw)
        self.nav_list = QListWidget()
        hb = QHBoxLayout(); self.btn_nav_add = QPushButton("Add"); self.btn_nav_del = QPushButton("Delete")
        hb.addWidget(self.btn_nav_add); hb.addWidget(self.btn_nav_del)
        vbox.addWidget(self.nav_list); vbox.addLayout(hb)
        self.meta_tab.addTab(navw, "Navigation")
        self.btn_nav_add.clicked.connect(lambda: self.nav_list.addItem("Text | /path"))
        self.btn_nav_del.clicked.connect(self._nav_del)

        # Revisions
        revw = QWidget(); rv = QVBoxLayout(revw)
        self.rev_table = QTableWidget(0, 4, self)
        self.rev_table.setHorizontalHeaderLabels(["Date","Rev","Description","By"])
        self.rev_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        rv.addWidget(self.rev_table)
        hb2 = QHBoxLayout()
        self.btn_rev_add_above = QPushButton("Add Above")
        self.btn_rev_add_below = QPushButton("Add Below")
        self.btn_rev_del = QPushButton("Delete")
        hb2.addWidget(self.btn_rev_add_above); hb2.addWidget(self.btn_rev_add_below); hb2.addWidget(self.btn_rev_del)
        rv.addLayout(hb2)
        self.btn_rev_add_above.clicked.connect(lambda: self._rev_insert(-1))
        self.btn_rev_add_below.clicked.connect(lambda: self._rev_insert(+1))
        self.btn_rev_del.clicked.connect(self._rev_delete)
        self.meta_tab.addTab(revw, "Revisions")

        # EAGLE Exports
        eaw = QWidget(); ev = QVBoxLayout(eaw)
        self.lbl_exports = QLabel("Netlist / Partlist / Pin Interface (from ../md/PN-REV_sch.md):")
        self.exports_text = QPlainTextEdit(); self.exports_text.setReadOnly(True)
        self.btn_reload_exports = QPushButton("Reload from md")
        self.btn_reload_exports.clicked.connect(self._reload_exports_from_md)
        ev.addWidget(self.lbl_exports); ev.addWidget(self.exports_text); ev.addWidget(self.btn_reload_exports)
        self.meta_tab.addTab(eaw, "EAGLE Exports")

        self.tabs.addTab(self.meta_tab, "Metadata")

        # Description
        w = QWidget(); v = QVBoxLayout(w)
        hb = QHBoxLayout()
        self.btn_edit_seeds = QPushButton("Edit AI Seeds…")
        self.cmb_maturity = QComboBox(); self.cmb_maturity.addItems(["Placeholder","Immature","Mature","Locked"])
        hb.addWidget(self.btn_edit_seeds); hb.addWidget(QLabel("Maturity:")); hb.addWidget(self.cmb_maturity); hb.addStretch(1)
        self.txt_description = QTextEdit()
        v.addLayout(hb); v.addWidget(self.txt_description)
        self.tabs.addTab(w, "Description")

        # Videos
        w = QWidget(); v = QVBoxLayout(w)
        self.videos_list = QListWidget()
        hb = QHBoxLayout(); self.btn_vid_add = QPushButton("Add URL"); self.btn_vid_del = QPushButton("Delete")
        hb.addWidget(self.btn_vid_add); hb.addWidget(self.btn_vid_del); hb.addStretch(1)
        v.addWidget(self.videos_list); v.addLayout(hb)
        self.tabs.addTab(w, "Videos")

        # Schematic
        w = QWidget(); v = QVBoxLayout(w)
        self.schematic_container = QVBoxLayout(); v.addLayout(self.schematic_container)
        self.tabs.addTab(w, "Schematic")

        # Layout
        w = QWidget(); v = QVBoxLayout(w)
        self.layout_container = QVBoxLayout(); v.addLayout(self.layout_container)
        self.tabs.addTab(w, "Layout")

        # Downloads
        w = QWidget(); v = QVBoxLayout(w)
        self.downloads_list = QListWidget()
        hb = QHBoxLayout(); self.btn_dl_add = QPushButton("Add"); self.btn_dl_del = QPushButton("Delete")
        hb.addWidget(self.btn_dl_add); hb.addWidget(self.btn_dl_del); hb.addStretch(1)
        v.addWidget(self.downloads_list); v.addLayout(hb)
        self.tabs.addTab(w, "Downloads")

        # Datasheets
        w = QWidget(); v = QVBoxLayout(w)
        if QWebEngineView:
            self.pdf_view = QWebEngineView()
            v.addWidget(self.pdf_view)
        else:
            self.pdf_view = None
            v.addWidget(QLabel("QtWebEngine not available."))
        self.tabs.addTab(w, "Datasheets")

        # Resources
        w = QWidget(); v = QVBoxLayout(w)
        self.resources_list = QListWidget()
        hb = QHBoxLayout(); self.btn_res_add = QPushButton("Add URL"); self.btn_res_del = QPushButton("Delete")
        hb.addWidget(self.btn_res_add); hb.addWidget(self.btn_res_del); hb.addStretch(1)
        v.addWidget(self.resources_list); v.addLayout(hb)
        self.tabs.addTab(w, "Resources")

        # FMEA
        w = QWidget(); v = QVBoxLayout(w)
        self.fmea_table = QTableWidget(0, 17, self)
        self.fmea_table.setHorizontalHeaderLabels([
            "Item","Potential Failure Mode","Potential Effect of Failure","Severity",
            "Potential Causes/Mechanisms","Occurrence","Current Process Controls","Detection",
            "RPN","Recommended Actions","Responsibility","Target Completion Date",
            "Actions Taken","Resulting Severity","Resulting Occurrence","Resulting Detection","New RPN"
        ])
        v.addWidget(self.fmea_table)
        hb = QHBoxLayout()
        self.btn_fmea_add_above = QPushButton("Add Above")
        self.btn_fmea_add_below = QPushButton("Add Below")
        self.btn_fmea_del = QPushButton("Delete")
        hb.addWidget(self.btn_fmea_add_above); hb.addWidget(self.btn_fmea_add_below); hb.addWidget(self.btn_fmea_del)
        v.addLayout(hb)
        self.btn_fmea_add_above.clicked.connect(lambda: self._table_insert(self.fmea_table, -1))
        self.btn_fmea_add_below.clicked.connect(lambda: self._table_insert(self.fmea_table, +1))
        self.btn_fmea_del.clicked.connect(lambda: self._table_delete(self.fmea_table))
        self.tabs.addTab(w, "FMEA")

        # Testing
        w = QWidget(); v = QVBoxLayout(w)
        self.testing_table = QTableWidget(0, 7, self)
        self.testing_table.setHorizontalHeaderLabels([
            "Test No.","Test Name","Test Description","Lower Limit","Target Value","Upper Limit","Units"
        ])
        v.addWidget(self.testing_table)
        hb = QHBoxLayout()
        self.btn_test_add_above = QPushButton("Add Above")
        self.btn_test_add_below = QPushButton("Add Below")
        self.btn_test_del = QPushButton("Delete")
        hb.addWidget(self.btn_test_add_above); hb.addWidget(self.btn_test_add_below); hb.addWidget(self.btn_test_del)
        v.addLayout(hb)
        self.btn_test_add_above.clicked.connect(lambda: self._table_insert(self.testing_table, -1))
        self.btn_test_add_below.clicked.connect(lambda: self._table_insert(self.testing_table, +1))
        self.btn_test_del.clicked.connect(lambda: self._table_delete(self.testing_table))
        self.tabs.addTab(w, "Testing")

        # Raw Text
        self._build_raw_text_tab()

    def _populate_board(self, meta: dict, html_text: str):
        # Basics
        self.in_pn.setText(meta.get("pn",""))
        self.in_title.setText(meta.get("title",""))
        # SEO
        seo = meta.get("seo",{})
        self.in_slogan.setText(seo.get("slogan",""))
        self.in_keywords.setText(",".join(seo.get("keywords",[])))
        self.in_description.setText(seo.get("description",""))
        # Navigation
        self.nav_list.clear()
        for item in meta.get("nav",[]):
            self.nav_list.addItem(f"{item.get('text','')} | {item.get('url','#')}")
        # Revisions
        self.rev_table.setRowCount(0)
        for r in meta.get("revisions",[]):
            rcount = self.rev_table.rowCount()
            self.rev_table.insertRow(rcount)
            self.rev_table.setItem(rcount,0,QTableWidgetItem(r.get("date","")))
            self.rev_table.setItem(rcount,1,QTableWidgetItem(r.get("rev","")))
            self.rev_table.setItem(rcount,2,QTableWidgetItem(r.get("desc","")))
            self.rev_table.setItem(rcount,3,QTableWidgetItem(r.get("by","")))

        # EAGLE exports
        self._reload_exports_from_md()
        # Raw text
        self.raw_text.setPlainText(html_text or "")

    # --- small helpers for board mode ---
    def _nav_del(self):
        for it in self.nav_list.selectedItems():
            self.nav_list.takeItem(self.nav_list.row(it))

    def _rev_insert(self, rel: int):
        row = self.rev_table.currentRow()
        if row < 0:
            row = self.rev_table.rowCount() - 1
        at = max(0, row + (0 if rel < 0 else 1))
        self.rev_table.insertRow(at)
        for c in range(4):
            self.rev_table.setItem(at, c, QTableWidgetItem(""))

    def _rev_delete(self):
        rows = sorted(set([i.row() for i in self.rev_table.selectedIndexes()]), reverse=True)
        for r in rows:
            self.rev_table.removeRow(r)

    def _reload_exports_from_md(self):
        if not self.current_path:
            self.exports_text.setPlainText("No current file."); return
        pn = self.in_pn.text().strip()
        rev = ""
        if self.rev_table.rowCount() > 0:
            last = self.rev_table.rowCount() - 1
            it = self.rev_table.item(last, 1)
            rev = it.text().strip() if it else ""
        text = ""
        try:
            md_dir = (self.current_path.parent / ".." / "md").resolve()
            if pn and rev:
                f = md_dir / f"{pn}-{rev}_sch.md"
                text = f.read_text(encoding="utf-8") if f.exists() else f"Not found: {f}"
            else:
                text = "PN or Rev missing."
        except Exception as e:
            text = str(e)
        self.exports_text.setPlainText(text)

    def _table_insert(self, table: QTableWidget, rel: int):
        row = table.currentRow()
        if row < 0:
            row = table.rowCount() - 1
        at = max(0, row + (0 if rel < 0 else 1))
        table.insertRow(at)
        for c in range(table.columnCount()):
            table.setItem(at, c, QTableWidgetItem(""))

    def _table_delete(self, table: QTableWidget):
        rows = sorted(set([i.row() for i in table.selectedIndexes()]), reverse=True)
        for r in rows:
            table.removeRow(r)

    # ---------------------- Raw Text ----------------------
    def _build_raw_text_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.raw_text = QPlainTextEdit(); self.raw_text.setReadOnly(True)
        v.addWidget(self.raw_text)
        self.tabs.addTab(w, "Raw Text")

    def _build_raw_only(self):
        self._build_raw_text_tab()
