import os, re, glob
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit, QListWidget,
    QPushButton, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QSplitter, QPlainTextEdit, QGroupBox, QComboBox, QFileDialog
)
from PyQt5.QtCore import Qt
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    from PyQt5.QtCore import QUrl
except Exception:
    QWebEngineView = None
    QUrl = None

from services.template_loader import Templates
from services.html_service import HtmlService

class MainTabs(QWidget):
    def __init__(self, ctx, get_editor_text_callable=None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.get_editor_text = get_editor_text_callable  # function to fetch current editor text
        self.current_path = None
        self.templates = None
        self.htmlsvc = None

        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        self.tabs = QTabWidget(self)
        lay.addWidget(self.tabs)

        # --- Build tabs ---
        self._build_metadata_tab()
        self._build_description_tab()
        self._build_videos_tab()
        self._build_schematic_tab()
        self._build_layout_tab()
        self._build_downloads_tab()
        self._build_datasheets_tab()
        self._build_resources_tab()
        self._build_fmea_tab()
        self._build_testing_tab()
        self._build_raw_text_tab()

    # ---------------------- Public API ----------------------
    def load_html_file(self, path: Path):
        self.current_path = Path(path)
        try:
            html_text = self.current_path.read_text(encoding="utf-8")
        except Exception:
            html_text = ""
        try:
            self.templates = Templates(self.ctx.templates_dir)
            self.htmlsvc = HtmlService(self.templates)
            meta = self.htmlsvc.extract_metadata(html_text) if html_text else {}
        except Exception:
            meta = {}

        self._populate_metadata(meta)
        self._populate_description(meta, html_text)
        self._populate_videos([])
        self._populate_schematic(meta)
        self._populate_layout(meta)
        self._populate_downloads([])
        self._populate_datasheet(meta)
        self._populate_resources([])
        # FMEA/Testing remain user-driven; leave as-is
        self._populate_raw_text(html_text)

    # ---------------------- Metadata Tab ----------------------
    def _build_metadata_tab(self):
        self.meta_tab = QTabWidget(self)
        self.tabs.addTab(self.meta_tab, "Metadata")

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
        self.btn_nav_add.clicked.connect(self._nav_add)
        self.btn_nav_del.clicked.connect(self._nav_del)
        self.meta_tab.addTab(navw, "Navigation")

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
        self.btn_rev_add_above.clicked.connect(lambda: self._rev_insert(relative=-1))
        self.btn_rev_add_below.clicked.connect(lambda: self._rev_insert(relative=+1))
        self.btn_rev_del.clicked.connect(self._rev_delete)
        self.meta_tab.addTab(revw, "Revisions")

        # EAGLE Exports
        eaw = QWidget(); ev = QVBoxLayout(eaw)
        self.lbl_exports = QLabel("Netlist / Partlist / Pin Interface:")
        self.exports_text = QPlainTextEdit(); self.exports_text.setReadOnly(True)
        self.btn_reload_exports = QPushButton("Reload from md")
        self.btn_reload_exports.clicked.connect(self._reload_exports_from_md)
        ev.addWidget(self.lbl_exports); ev.addWidget(self.exports_text); ev.addWidget(self.btn_reload_exports)
        self.meta_tab.addTab(eaw, "EAGLE Exports")

    def _populate_metadata(self, meta: dict):
        self.in_pn.setText(meta.get("pn",""))
        self.in_title.setText(meta.get("title",""))
        # board/pieces/panel not parsed yet; leave editable blanks
        seo = meta.get("seo",{})
        self.in_slogan.setText(seo.get("slogan",""))
        self.in_keywords.setText(",".join(seo.get("keywords",[])))
        self.in_description.setText(seo.get("description",""))
        # nav
        self.nav_list.clear()
        for item in meta.get("nav",[]):
            self.nav_list.addItem(f"{item.get('text','')} | {item.get('url','#')}")
        # revisions
        self.rev_table.setRowCount(0)
        for r in meta.get("revisions",[]):
            rcount = self.rev_table.rowCount()
            self.rev_table.insertRow(rcount)
            self.rev_table.setItem(rcount,0,QTableWidgetItem(r.get("date","")))
            self.rev_table.setItem(rcount,1,QTableWidgetItem(r.get("rev","")))
            self.rev_table.setItem(rcount,2,QTableWidgetItem(r.get("desc","")))
            self.rev_table.setItem(rcount,3,QTableWidgetItem(r.get("by","")))
        # eager load exports
        self._reload_exports_from_md()

    def _nav_add(self):
        self.nav_list.addItem("Text | /path")

    def _nav_del(self):
        for it in self.nav_list.selectedItems():
            self.nav_list.takeItem(self.nav_list.row(it))

    def _rev_insert(self, relative: int):
        row = self.rev_table.currentRow()
        if row < 0:
            row = self.rev_table.rowCount() - 1
        insert_at = max(0, row + (0 if relative < 0 else 1))
        self.rev_table.insertRow(insert_at)
        for c in range(4):
            self.rev_table.setItem(insert_at, c, QTableWidgetItem(""))

    def _rev_delete(self):
        rows = sorted(set([i.row() for i in self.rev_table.selectedIndexes()]), reverse=True)
        for r in rows:
            self.rev_table.removeRow(r)

    def _reload_exports_from_md(self):
        pn = self.in_pn.text().strip()
        # choose last rev row if any
        rev = ""
        if self.rev_table.rowCount() > 0:
            last = self.rev_table.rowCount() - 1
            it = self.rev_table.item(last, 1)
            rev = it.text().strip() if it else ""
        # compute md file path: ../md/PN-REV_sch.md
        text = ""
        try:
            if self.current_path:
                md_dir = (self.current_path.parent / ".." / "md").resolve()
                if pn and rev:
                    f = md_dir / f"{pn}-{rev}_sch.md"
                    if f.exists():
                        text = f.read_text(encoding="utf-8")
                    else:
                        text = f"Not found: {f}"
                else:
                    text = "PN or Rev missing."
            else:
                text = "No current file."
        except Exception as e:
            text = str(e)
        self.exports_text.setPlainText(text)

    # ---------------------- Description ----------------------
    def _build_description_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        hb = QHBoxLayout()
        self.btn_edit_seeds = QPushButton("Edit AI Seeds…")
        self.cmb_maturity = QComboBox(); self.cmb_maturity.addItems(["Placeholder","Immature","Mature","Locked"])
        hb.addWidget(self.btn_edit_seeds); hb.addWidget(QLabel("Maturity:")); hb.addWidget(self.cmb_maturity); hb.addStretch(1)
        self.txt_description = QTextEdit()
        v.addLayout(hb); v.addWidget(self.txt_description)
        self.tabs.addTab(w, "Description")

    def _populate_description(self, meta: dict, html_text: str):
        # leave description empty; user/AI fills here
        pass

    # ---------------------- Videos ----------------------
    def _build_videos_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.videos_list = QListWidget()
        hb = QHBoxLayout(); self.btn_vid_add = QPushButton("Add URL"); self.btn_vid_del = QPushButton("Delete")
        hb.addWidget(self.btn_vid_add); hb.addWidget(self.btn_vid_del); hb.addStretch(1)
        v.addWidget(self.videos_list); v.addLayout(hb)
        self.tabs.addTab(w, "Videos")

    def _populate_videos(self, items):
        self.videos_list.clear()
        for url in items:
            self.videos_list.addItem(url)

    # ---------------------- Schematic ----------------------
    def _build_schematic_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.schematic_container = QVBoxLayout(); v.addLayout(self.schematic_container)
        self.tabs.addTab(w, "Schematic")

    def _populate_schematic(self, meta: dict):
        # clear existing
        while self.schematic_container.count():
            item = self.schematic_container.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()
        pn = self.in_pn.text().strip()
        if not self.current_path or not pn:
            self.schematic_container.addWidget(QLabel("PN missing or no file loaded.")); return
        img_dir = (self.current_path.parent / ".." / "images").resolve()
        i = 1
        found = False
        while True:
            p = img_dir / f"{pn}_schematic_{i:02d}.png"
            if p.exists():
                lbl = QLabel(f"{p.name}")
                img = QLabel(); img.setText(f"[image would display here]\n{p}")
                img.setAlignment(Qt.AlignCenter)
                gb = QGroupBox(p.name); vb = QVBoxLayout(gb); vb.addWidget(lbl); vb.addWidget(img)
                self.schematic_container.addWidget(gb)
                found = True
                i += 1
            else:
                break
        if not found:
            self.schematic_container.addWidget(QLabel("No schematic images found."))

    # ---------------------- Layout ----------------------
    def _build_layout_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.layout_container = QVBoxLayout(); v.addLayout(self.layout_container)
        self.tabs.addTab(w, "Layout")

    def _populate_layout(self, meta: dict):
        while self.layout_container.count():
            item = self.layout_container.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()
        pn = self.in_pn.text().strip()
        if not self.current_path or not pn:
            self.layout_container.addWidget(QLabel("PN missing or no file loaded.")); return
        img_dir = (self.current_path.parent / ".." / "images").resolve()
        p = img_dir / f"{pn}_components_top.png"
        if p.exists():
            lbl = QLabel(p.name)
            img = QLabel(); img.setText(f"[image would display here]\n{p}")
            img.setAlignment(Qt.AlignCenter)
            gb = QGroupBox(p.name); vb = QVBoxLayout(gb); vb.addWidget(lbl); vb.addWidget(img)
            self.layout_container.addWidget(gb)
        else:
            self.layout_container.addWidget(QLabel("Layout image not found."))

    # ---------------------- Downloads ----------------------
    def _build_downloads_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.downloads_list = QListWidget()
        hb = QHBoxLayout(); self.btn_dl_add = QPushButton("Add"); self.btn_dl_del = QPushButton("Delete")
        hb.addWidget(self.btn_dl_add); hb.addWidget(self.btn_dl_del); hb.addStretch(1)
        v.addWidget(self.downloads_list); v.addLayout(hb)
        self.tabs.addTab(w, "Downloads")

    def _populate_downloads(self, items):
        self.downloads_list.clear()
        for item in items:
            self.downloads_list.addItem(item)

    # ---------------------- Datasheets ----------------------
    def _build_datasheets_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        if QWebEngineView:
            self.pdf_view = QWebEngineView()
            v.addWidget(self.pdf_view)
        else:
            self.pdf_view = None
            v.addWidget(QLabel("QtWebEngine not available."))
        self.tabs.addTab(w, "Datasheets")

    def _populate_datasheet(self, meta: dict):
        if not self.current_path or self.pdf_view is None:
            return
        pn = self.in_pn.text().strip()
        pdf = (self.current_path.parent / ".." / "datasheets" / f"{pn}.pdf").resolve()
        if pdf.exists():
            self.pdf_view.load(QUrl.fromLocalFile(str(pdf)))
        else:
            # Clear or show placeholder
            pass

    # ---------------------- Resources ----------------------
    def _build_resources_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.resources_list = QListWidget()
        hb = QHBoxLayout(); self.btn_res_add = QPushButton("Add URL"); self.btn_res_del = QPushButton("Delete")
        hb.addWidget(self.btn_res_add); hb.addWidget(self.btn_res_del); hb.addStretch(1)
        v.addWidget(self.resources_list); v.addLayout(hb)
        self.tabs.addTab(w, "Resources")

    def _populate_resources(self, items):
        self.resources_list.clear()
        for url in items:
            self.resources_list.addItem(url)

    # ---------------------- FMEA ----------------------
    def _build_fmea_tab(self):
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

    # ---------------------- Testing ----------------------
    def _build_testing_tab(self):
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

    def _populate_raw_text(self, text: str):
        self.raw_text.setPlainText(text)
