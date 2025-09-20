#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
miniPCB Catalog — PyQt5 (HTML Editor, Description AI)
Dark theme • HTML-first • Fixed Site Tabs + Collections • Image previews
Autosave (30s) + Dirty indicator • Description AI (seed → generated) with ETA
Persists AI timing stats in minipcb_catalog.json

New in this build
- Collection table: right-click → "Add row above / below"
- Navigation tab (both Detail & Collection views): edit the top-of-page nav links
- New-file wizard prompts for collection pages to include in nav (links + labels)
- New-file template includes chosen nav links (not just Home)
- Review pane reflects latest form state (including Navigation)

Notes
- OpenAI usage is optional and entirely local (no backend). Reads OPENAI_API_KEY and OPENAI_MODEL (default "gpt-5").
- Timing stats (for ETA): content_root / minipcb_catalog.json
"""

from __future__ import annotations
import sys, os, re, json, shutil, subprocess, datetime, platform, time
from pathlib import Path
from typing import Optional, Tuple, List
from urllib.parse import urlparse, unquote

# ---- HTML parsing
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except Exception:
    BS4_AVAILABLE = False

# ---- OpenAI (optional; only used for Description generation)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except Exception:
    OpenAI = None
    OPENAI_AVAILABLE = False

from PyQt5.QtCore import Qt, QSortFilterProxyModel, QModelIndex, QSettings, QTimer, QThread, pyqtSignal, QPoint
from PyQt5.QtGui import QKeySequence, QIcon, QPixmap, QPainter, QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFileSystemModel, QTreeView, QToolBar, QAction, QFileDialog,
    QInputDialog, QMessageBox, QLabel, QAbstractItemView, QFormLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QSplitter, QTabWidget, QTextEdit, QStyleFactory, QMenu,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem
)

APP_TITLE = "miniPCB Catalog"

# ---------- Windows dark titlebar ----------
if platform.system() == "Windows":
    import ctypes
    from ctypes import wintypes
    def _set_win_dark_titlebar(hwnd: int, enabled: bool = True):
        try:
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
            attribute = wintypes.DWORD(DWMWA_USE_IMMERSIVE_DARK_MODE)
            pv = ctypes.c_int(1 if enabled else 0)
            dwm = ctypes.WinDLL("dwmapi")
            res = dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), attribute, ctypes.byref(pv), ctypes.sizeof(pv))
            if res != 0:
                attribute = wintypes.DWORD(DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1)
                dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), attribute, ctypes.byref(pv), ctypes.sizeof(pv))
        except Exception:
            pass
    def apply_windows_dark_titlebar(widget):
        try:
            hwnd = int(widget.winId()); _set_win_dark_titlebar(hwnd, True)
        except Exception: pass
else:
    def apply_windows_dark_titlebar(widget): pass

def today_iso() -> str:
    return datetime.date.today().isoformat()

def now_stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# ---------- Settings ----------
SETTINGS_ORG = "miniPCB"
SETTINGS_APP = "miniPCB Catalog"
KEY_CONTENT_DIR = "content_dir"
KEY_OPENAI_MODEL = "openai_model"
KEY_OPENAI_KEY = "openai_key"

def get_settings() -> QSettings:
    return QSettings(SETTINGS_ORG, SETTINGS_APP)

def default_content_root() -> Path:
    here = Path(__file__).resolve()
    if here.parent.name.lower() == "scripts":
        return here.parent.parent
    return Path.cwd()

# ---------- Helpers ----------
def ascii_sanitize(text: str) -> str:
    if not text: return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
    return text

def condense_meta(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def make_emoji_icon(emoji: str, px: int = 256) -> QIcon:
    pm = QPixmap(px, px); pm.fill(Qt.transparent)
    p = QPainter(pm)
    try:
        f = QFont("Segoe UI Emoji", int(px * 0.66))
        f.setStyleStrategy(QFont.PreferAntialias); p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignCenter, emoji)
    finally:
        p.end()
    return QIcon(pm)

def strip_inline_styles_from_fragment(html: str) -> str:
    """Remove inline styles and Qt spans from a small HTML fragment."""
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(True):
            if tag.has_attr("style"):
                del tag["style"]
            if tag.has_attr("-qt-block-indent"):
                del tag["-qt-block-indent"]
            if tag.name == "span" and not tag.attrs:
                tag.unwrap()
        allowed = {"p","ul","ol","li","div","section","h3","h4","strong","em","code","pre","br"}
        for tag in soup.find_all(True):
            if tag.name not in allowed:
                tag.name = "div"
        return soup.decode()
    except Exception:
        return re.sub(r'\sstyle="[^"]*"', "", html)

def compact_html_for_readability(soup) -> str:
    """
    Compact pretty-print without wrecking tables/lists; keeps output readable.
    """
    txt = str(soup)
    txt = re.sub(r">\s+<", "><", txt)
    txt = re.sub(r"(</(h[1-6]|p|div|section|header|footer|main|nav)>)", r"\1\n", txt)
    txt = re.sub(r"(<(ul|ol|li|table|thead|tbody|tfoot|tr|th|td)[^>]*>)", r"\n\1", txt)
    txt = re.sub(r"(</(ul|ol|li|table|thead|tbody|tfoot|tr|th|td)>)", r"\1\n", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    txt = re.sub(r">\s{2,}", "> ", txt)
    txt = re.sub(r"\s{2,}<", " <", txt)
    return txt.strip()

# ---------- Preview label ----------
class PreviewLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix: Optional[QPixmap] = None
        self.setMinimumHeight(220)
        self.setAlignment(Qt.AlignCenter)
        self.setText("(no image)")
        self.setStyleSheet("QLabel { border:1px solid #3A3F44; border-radius:6px; padding:6px; }")

    def set_pixmap(self, pix: Optional[QPixmap]):
        self._pix = pix
        self._render()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._render()

    def _render(self):
        if not self._pix or self._pix.isNull():
            self.setText("(no image)")
            self.setPixmap(QPixmap())
            return
        w = max(64, self.width() - 12)
        h = max(64, self.height() - 12)
        scaled = self._pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)
        self.setText("")

# ---------- Proxy model ----------
class DescProxyModel(QSortFilterProxyModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._title_cache = {}

    def filterAcceptsRow(self, source_row, source_parent):
        sm = self.sourceModel()
        idx = sm.index(source_row, 0, source_parent)
        if not idx.isValid(): return False
        if sm.isDir(idx): return True
        name = sm.fileName(idx).lower()
        return name.endswith(".html") or name.endswith(".htm")

    def columnCount(self, parent):
        return max(2, super().columnCount(parent))

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        if index.column() == 0:
            return super().data(index, role)
        if index.column() == 1 and role in (Qt.DisplayRole, Qt.ToolTipRole):
            sidx = self.mapToSource(index.sibling(index.row(), 0))
            path = Path(self.sourceModel().filePath(sidx))
            key = str(path)
            val = self._title_cache.get(key)
            if val is None:
                val = self._read_title_from_html(path)
                self._title_cache[key] = val
            return val
        if index.column() >= 2 and role == Qt.DisplayRole:
            return ""
        return super().data(index, role)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return ["Name", "Title"][section] if section in (0, 1) else super().headerData(section, orientation, role)
        return super().headerData(section, orientation, role)

    def refresh_desc(self, path: Path):
        self._title_cache.pop(str(path), None)
        sm = self.sourceModel()
        sidx = sm.index(str(path))
        if sidx.isValid():
            pidx = self.mapFromSource(sidx)
            if pidx.isValid():
                cell = pidx.sibling(pidx.row(), 1)
                self.dataChanged.emit(cell, cell, [Qt.DisplayRole, Qt.ToolTipRole])

    @staticmethod
    def _read_title_from_html(path: Path) -> str:
        try:
            txt = path.read_text(encoding="utf-8")
            if BS4_AVAILABLE:
                soup = BeautifulSoup(txt, "html.parser")
                return (soup.title.string.strip() if soup.title and soup.title.string else "")
            m = re.search(r"<title>(.*?)</title>", txt, re.I | re.S)
            return (m.group(1).strip() if m else "")
        except Exception:
            return ""

# ---------- AI Worker for Description ----------
class DescAIWorker(QThread):
    finished = pyqtSignal(dict)  # {"ok":True,"html":str,"elapsed":float} OR {"ok":False,"error":str,"elapsed":float}

    def __init__(self, api_key: str, model_name: str, seed_text: str, page_title: str, h1: str, part_no: str, timeout: int = 120):
        super().__init__()
        self.api_key = api_key
        self.model = model_name
        self.seed = seed_text or ""
        self.page_title = page_title or ""
        self.h1 = h1 or ""
        self.part_no = part_no or ""
        self.timeout = timeout

    def run(self):
        start = time.time()
        try:
            if not OPENAI_AVAILABLE:
                raise RuntimeError("OpenAI SDK not installed. Install with: pip install openai")
            if not self.api_key:
                raise RuntimeError("OPENAI_API_KEY not set. Set it in the app or via env.")

            client = OpenAI(api_key=self.api_key)

            sys_prompt = (
                "You are an expert technical copywriter for a hardware mini PCB catalog.\n"
                "Write crisp, accurate, helpful product descriptions for electronic circuit boards.\n"
                "Return ONLY an HTML fragment (divs, p, ul/li, h3/h4 ok). No <html>, <head>, or <body>."
            )
            user_prompt = (
                f"PAGE CONTEXT:\n"
                f"- Page Title: {self.page_title}\n"
                f"- H1: {self.h1}\n"
                f"- Part No: {self.part_no}\n\n"
                f"SEED (editor-provided):\n{self.seed}\n\n"
                "TASK:\n"
                "• Generate a concise, skimmable description suitable for the page's Description tab.\n"
                "• Include 2–4 short paragraphs and, if helpful, ONE bullet list (3–6 items max).\n"
                "• Avoid marketing fluff; focus on what the circuit does, how it works, notable components/constraints,\n"
                "  and typical use-cases. ~180–260 words total.\n"
                "• Use neutral, professional tone. Use <strong> sparingly for key specs.\n"
                "• Output: ONLY an HTML fragment. No outer wrapper beyond section-level tags."
            )

            html = ""
            try:
                resp = client.responses.create(
                    model=self.model,
                    input=[{"role":"system","content":sys_prompt},{"role":"user","content":user_prompt}],
                    timeout=self.timeout,
                )
                html = getattr(resp, "output_text", None) or ""
                if not html:
                    try:
                        html = resp.output[0].content[0].text
                    except Exception:
                        html = ""
            except Exception:
                cc = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role":"system","content":sys_prompt},{"role":"user","content":user_prompt}],
                    timeout=self.timeout,
                )
                try:
                    html = cc.choices[0].message.content or ""
                except Exception:
                    html = ""

            if not html:
                raise RuntimeError("Model returned empty content.")

            html = html.strip()
            elapsed = time.time() - start
            self.finished.emit({"ok": True, "html": html, "elapsed": elapsed})
        except Exception as e:
            elapsed = time.time() - start
            self.finished.emit({"ok": False, "error": str(e), "elapsed": elapsed})

# ---------- New-file: choose nav links dialog ----------
class NavPickerDialog(QDialog):
    def __init__(self, parent, candidates: List[Tuple[str,str,Path]], base_dir: Path):
        """
        candidates: list of (label, href, path)
        """
        super().__init__(parent)
        self.setWindowTitle("Choose Navigation Links")
        self.resize(520, 540)
        v = QVBoxLayout(self)
        lab = QLabel("Select collection pages to include in the navigation bar.\n(Home is always included.)")
        v.addWidget(lab)
        self.list = QListWidget(self)
        self.list.setSelectionMode(QListWidget.NoSelection)
        v.addWidget(self.list, 1)

        # Populate
        for label, href, p in candidates:
            item = QListWidgetItem(f"{label}  —  {href}")
            item.setData(Qt.UserRole, (label, href))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # Pre-check items in the same folder as base_dir
            item.setCheckState(Qt.Checked if p.parent.resolve() == base_dir.resolve() else Qt.Unchecked)
            self.list.addItem(item)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def selected_links(self) -> List[Tuple[str,str]]:
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == Qt.Checked:
                out.append(it.data(Qt.UserRole))
        return out

# ---------- Main Window ----------
class CatalogWindow(QMainWindow):
    def __init__(self, content_root: Path, app_icon: QIcon):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon)
        self.resize(1440, 920)

        self.content_root = content_root
        self.current_path: Optional[Path] = None
        self._review_dirty = False
        self._dirty = False
        self._loading = False
        self._desc_generated_raw = ""  # saved verbatim; sanitized (no inline styles)

        # OpenAI settings
        s = get_settings()
        self.openai_model = s.value(KEY_OPENAI_MODEL, os.environ.get("OPENAI_MODEL", "gpt-5"))
        self.openai_key = s.value(KEY_OPENAI_KEY, os.environ.get("OPENAI_API_KEY", ""))

        # Autosave
        self.autosave_interval = 30
        self.autosave_secs_left = self.autosave_interval
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._autosave_tick)
        self.autosave_timer.start(1000)

        # AI timers/stats
        self.ai_timer = QTimer(self)
        self.ai_timer.timeout.connect(self._tick_ai_ui)
        self._ai_start_ts: Optional[datetime.datetime] = None
        self._ai_eta_sec: Optional[int] = None
        self._ai_running = False

        # Toolbar
        tb = QToolBar("Main", self); tb.setMovable(False); self.addToolBar(tb)
        act_new_entry = QAction("🧩 New Entry", self);  act_new_entry.triggered.connect(self.create_new_entry);  tb.addAction(act_new_entry)
        act_new_folder = QAction("🗂️ New Folder", self); act_new_folder.triggered.connect(self.create_new_folder); tb.addAction(act_new_folder)
        act_rename     = QAction("✏️ Rename", self);     act_rename.triggered.connect(self.rename_item);           tb.addAction(act_rename)
        act_delete     = QAction("🗑️ Delete", self);     act_delete.triggered.connect(self.delete_item);           tb.addAction(act_delete)
        tb.addSeparator()
        act_open_loc = QAction("📂 Open Location", self); act_open_loc.triggered.connect(self.open_file_location); tb.addAction(act_open_loc)
        tb.addSeparator()
        self.act_save = QAction("💾 Save (Ctrl+S)", self); self.act_save.setShortcut(QKeySequence.Save)
        self.act_save.triggered.connect(self.save_from_form); tb.addAction(self.act_save)
        tb.addSeparator()
        act_set_model = QAction("🤖 Set Model…", self); act_set_model.triggered.connect(self._set_model); tb.addAction(act_set_model)
        act_set_key   = QAction("🔑 Set API Key…", self); act_set_key.triggered.connect(self._set_api_key); tb.addAction(act_set_key)

        # FS model + tree
        self.fs_model = QFileSystemModel(self); self.fs_model.setReadOnly(False)
        self.fs_model.setRootPath(str(self.content_root))
        self.fs_model.setNameFilters(["*.html", "*.htm"]); self.fs_model.setNameFilterDisables(False)

        self.proxy = DescProxyModel(self); self.proxy.setSourceModel(self.fs_model)

        self.tree = QTreeView(self); self.tree.setModel(self.proxy)
        self.tree.setRootIndex(self.proxy.mapFromSource(self.fs_model.index(str(self.content_root))))
        self.tree.setHeaderHidden(False); self.tree.setSortingEnabled(True); self.tree.sortByColumn(0, Qt.AscendingOrder)
        for col in range(2, self.proxy.columnCount(self.tree.rootIndex())): self.tree.setColumnHidden(col, True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.selectionModel().selectionChanged.connect(self.on_tree_selection)

        # Right panel
        right = QWidget(self); right_v = QVBoxLayout(right); right_v.setContentsMargins(0,0,0,0); right_v.setSpacing(8)
        top_row = QHBoxLayout()
        self.path_label = QLabel("", self)
        self.autosave_label = QLabel("Autosave in: -", self)
        self.autosave_label.setStyleSheet("color:#A0E0A0;")
        top_row.addWidget(self.path_label)
        top_row.addStretch(1)
        top_row.addWidget(self.autosave_label)
        right_v.addLayout(top_row)

        # Tabs holder
        self.tabs = QTabWidget(self)

        # Metadata tab — VERTICAL
        self.meta_tab = QWidget(self)
        meta_form = QFormLayout(self.meta_tab); meta_form.setVerticalSpacing(8)
        self.ed_title = QLineEdit(); self.ed_title.setPlaceholderText("<title>…")
        self.ed_keywords = QTextEdit(); self.ed_keywords.setPlaceholderText("meta keywords, comma-separated")
        self.ed_keywords.setAcceptRichText(False); self.ed_keywords.setMinimumHeight(60)
        self.ed_description = QTextEdit(); self.ed_description.setPlaceholderText("meta description")
        self.ed_description.setAcceptRichText(False); self.ed_description.setMinimumHeight(100)
        self.ed_h1 = QLineEdit(); self.ed_h1.setPlaceholderText("page H1…")
        self.ed_slogan = QLineEdit(); self.ed_slogan.setPlaceholderText('slogan paragraph…')
        meta_form.addRow("Title:", self.ed_title)
        meta_form.addRow("Meta Keywords:", self.ed_keywords)
        meta_form.addRow("Meta Description:", self.ed_description)
        meta_form.addRow("H1:", self.ed_h1)
        meta_form.addRow("Slogan:", self.ed_slogan)
        self.tabs.addTab(self.meta_tab, "Metadata")

        # Navigation tab (new)
        self.nav_tab = QWidget(self)
        nav_v = QVBoxLayout(self.nav_tab); nav_v.setContentsMargins(0,0,0,0)
        self.nav_table = QTableWidget(0, 2)
        self.nav_table.setHorizontalHeaderLabels(["Label", "Href"])
        self.nav_table.verticalHeader().setVisible(False)
        self.nav_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.nav_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        nav_v.addWidget(self.nav_table, 1)
        nav_btns = QHBoxLayout()
        b_nav_add = QPushButton("Add Link"); b_nav_del = QPushButton("Remove Selected")
        b_nav_add.clicked.connect(lambda: (self.nav_table.insertRow(self.nav_table.rowCount()), self._on_any_changed()))
        b_nav_del.clicked.connect(lambda: (self.nav_table.removeRow(self.nav_table.currentRow()) if self.nav_table.currentRow()>=0 else None, self._on_any_changed()))
        nav_btns.addWidget(b_nav_add); nav_btns.addWidget(b_nav_del); nav_btns.addStretch(1)
        nav_v.addLayout(nav_btns)
        self.tabs.addTab(self.nav_tab, "Navigation")
        self._install_row_context_menu(self.nav_table)  # bonus: same convenience menu

        # Sections (Detail pages)
        self.sections_host = QWidget(self); sh_v = QVBoxLayout(self.sections_host); sh_v.setContentsMargins(0,0,0,0)
        self.sections_tabs = QTabWidget(self.sections_host); sh_v.addWidget(self.sections_tabs, 1)
        self.tabs.addTab(self.sections_host, "Sections")
        self._build_fixed_section_editors()

        # Page mode (detail vs collection)
        self.page_mode = "detail"

        # Collection editor (Group/Collection pages)
        self.collection_host = QWidget(self); col_v = QVBoxLayout(self.collection_host); col_v.setContentsMargins(0,0,0,0); col_v.setSpacing(8)
        self.collection_tbl = QTableWidget(0, 4)
        self.collection_tbl.setHorizontalHeaderLabels(["Part No", "Title Text", "Href", "Pieces per Panel"])
        self.collection_tbl.verticalHeader().setVisible(False)
        self.collection_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.collection_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.collection_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.collection_tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        col_v.addWidget(self.collection_tbl, 1)
        row = QHBoxLayout()
        b_add = QPushButton("Add Row"); b_del = QPushButton("Remove Selected")
        b_add.clicked.connect(lambda: (self.collection_tbl.insertRow(self.collection_tbl.rowCount()), self._on_any_changed()))
        b_del.clicked.connect(lambda: (self.collection_tbl.removeRow(self.collection_tbl.currentRow()) if self.collection_tbl.currentRow()>=0 else None, self._on_any_changed()))
        row.addWidget(b_add); row.addWidget(b_del); row.addStretch(1)
        col_v.addLayout(row)
        self.tabs.addTab(self.collection_host, "Collection")
        # Context menu for collection table (requested)
        self.collection_tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.collection_tbl.customContextMenuRequested.connect(self._collection_context_menu)

        self.idx_sections_tab = self.tabs.indexOf(self.sections_host)
        self.idx_collection_tab = self.tabs.indexOf(self.collection_host)
        self._supports_tab_visible = hasattr(self.tabs, "setTabVisible")
        self._switch_page_mode("detail")

        # Review (raw)
        self.review_tab = QWidget(self); rv = QVBoxLayout(self.review_tab)
        self.review_raw = QTextEdit(self.review_tab); self.review_raw.setLineWrapMode(QTextEdit.NoWrap)
        self.review_raw.textChanged.connect(self._on_review_changed)
        rv.addWidget(self.review_raw)
        self.tabs.addTab(self.review_tab, "Review")

        # Stats
        self.stats_tab = QWidget(self); st = QFormLayout(self.stats_tab)
        self.stat_lines = QLabel("-"); self.stat_words = QLabel("-")
        self.stat_chars = QLabel("-"); self.stat_edited = QLabel("-")
        st.addRow("Line count:", self.stat_lines)
        st.addRow("Word count:", self.stat_words)
        st.addRow("Character count:", self.stat_chars)
        st.addRow("Last edited:", self.stat_edited)
        self.tabs.addTab(self.stats_tab, "Stats")

        # After all tabs exist, wire currentChanged (keeps Review synced)
        self.tabs.currentChanged.connect(self._on_tabs_changed)

        right_v.addWidget(self.tabs, 1)

        # Splitter
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self.tree); splitter.addWidget(right)
        splitter.setStretchFactor(0, 1); splitter.setStretchFactor(1, 2); splitter.setSizes([420, 980])

        central = QWidget(self); outer = QHBoxLayout(central); outer.setContentsMargins(8,8,8,8); outer.setSpacing(8)
        outer.addWidget(splitter); self.setCentralWidget(central)

        self.apply_dark_styles()
        apply_windows_dark_titlebar(self)
        self._set_dirty(False)

        if not BS4_AVAILABLE:
            self._info("BeautifulSoup not found",
                       "Install with:\n\n    pip install beautifulsoup4\n\n"
                       "You can still use the Review tab to edit raw HTML.")

    # ---------- Styling ----------
    def apply_dark_styles(self):
        self.setStyleSheet("""
            QWidget { background-color:#202225; color:#E6E6E6; }
            QToolBar { background:#1B1E20; spacing:6px; border:0; }
            QToolButton, QPushButton { color:#E6E6E6; }
            QLabel { color:#E6E6E6; }
            QLineEdit, QTextEdit { background:#2A2D31; color:#E6E6E6;
                                   border:1px solid #3A3F44; border-radius:6px; padding:6px; }
            QPushButton { background:#2F343A; border:1px solid #444; border-radius:6px; padding:6px 12px; }
            QPushButton:hover { background:#3A4047; } QPushButton:pressed { background:#2A2F35; }
            QTreeView { background:#1E2124; border:1px solid #3A3F44; }
            QTreeView::item:selected { background:#3B4252; color:#E6E6E6; }
            QHeaderView::section { background:#2A2D31; color:#E6E6E6; border:0; padding:6px; font-weight:600; }
            QTabBar::tab { background:#2A2D31; color:#E6E6E6; padding:8px 12px; margin-right:2px;
                           border-top-left-radius:6px; border-top-right-radius:6px; }
            QTabBar::tab:selected { background:#3A3F44; } QTabBar::tab:hover { background:#34383D; }
            QTableWidget { background:#1E2124; color:#E6E6E6; gridline-color:#3A3F44;
                           border:1px solid #3A3F44; border-radius:6px; }
            QMenu { background:#2A2D31; color:#E6E6E6; border:1px solid #3A3F44; }
        """)

    # ---------- Dialog helpers ----------
    def _ask_text(self, title: str, label: str, default: str = "") -> Tuple[str, bool]:
        dlg = QInputDialog(self); dlg.setWindowTitle(title); dlg.setLabelText(label); dlg.setTextValue(default)
        apply_windows_dark_titlebar(dlg)
        ok = dlg.exec_() == dlg.Accepted
        return (dlg.textValue(), ok)

    def _ask_yes_no(self, title: str, text: str) -> bool:
        mb = QMessageBox(self); mb.setWindowTitle(title); mb.setText(text)
        mb.setIcon(QMessageBox.Question); mb.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        apply_windows_dark_titlebar(mb)
        return mb.exec_() == mb.Yes

    def _info(self, title: str, text: str):
        mb = QMessageBox(self); mb.setWindowTitle(title); mb.setText(text)
        mb.setIcon(QMessageBox.Information); mb.setStandardButtons(QMessageBox.Ok); apply_windows_dark_titlebar(mb); mb.exec_()

    def _warn(self, title: str, text: str):
        mb = QMessageBox(self); mb.setWindowTitle(title); mb.setText(text)
        mb.setIcon(QMessageBox.Warning); mb.setStandardButtons(QMessageBox.Ok); apply_windows_dark_titlebar(mb); mb.exec_()

    def _error(self, title: str, text: str):
        mb = QMessageBox(self); mb.setWindowTitle(title); mb.setText(text)
        mb.setIcon(QMessageBox.Critical); mb.setStandardButtons(QMessageBox.Ok); apply_windows_dark_titlebar(mb); mb.exec_()

    # ---------- Fixed Sections UI (Detail pages) ----------
    def _build_fixed_section_editors(self):
        # Details form — VERTICAL
        w_details = QWidget()
        det_form = QFormLayout(w_details)
        det_form.setVerticalSpacing(8)
        self.det_part = QLineEdit()
        self.det_title = QLineEdit()
        self.det_board = QLineEdit()
        self.det_pieces = QLineEdit()
        self.det_panel = QLineEdit()
        det_form.addRow("Part No:", self.det_part)
        det_form.addRow("Title:", self.det_title)
        det_form.addRow("Board Size:", self.det_board)
        det_form.addRow("Pieces per Panel:", self.det_pieces)
        det_form.addRow("Panel Size:", self.det_panel)
        for ed in (self.det_part, self.det_title, self.det_board, self.det_pieces, self.det_panel):
            ed.textChanged.connect(self._on_any_changed)
        # auto-fill schematic/layout when part number changes
        self.det_part.textChanged.connect(self._on_partno_changed_update_paths)
        self.sections_tabs.addTab(w_details, "Details")

        # Description (NEW): seed + generated + AI controls
        w_desc = QWidget()
        vdesc = QVBoxLayout(w_desc); vdesc.setSpacing(8); vdesc.setContentsMargins(6,6,6,6)

        seed_box = QGroupBox("Seed")
        seed_form = QVBoxLayout(seed_box)
        self.desc_seed = QTextEdit(); self.desc_seed.setAcceptRichText(False); self.desc_seed.setPlaceholderText("Short notes, bullet points, or a rough paragraph to guide AI…")
        self.desc_seed.setMinimumHeight(100)
        self.desc_seed.textChanged.connect(self._on_any_changed)
        seed_form.addWidget(self.desc_seed)

        gen_box = QGroupBox("AI Generated")
        gen_v = QVBoxLayout(gen_box)
        self.desc_generated = QTextEdit(); self.desc_generated.setReadOnly(True); self.desc_generated.setAcceptRichText(True)
        self.desc_generated.setMinimumHeight(140)
        gen_v.addWidget(self.desc_generated)

        controls = QHBoxLayout()
        self.btn_desc_generate = QPushButton("Generate")
        self.btn_desc_generate.clicked.connect(self._start_desc_ai)
        self.lbl_desc_ai = QLabel("AI: idle")
        self.lbl_desc_ai.setStyleSheet("color:#C8E6C9;")
        controls.addWidget(self.btn_desc_generate)
        controls.addSpacing(12)
        controls.addWidget(self.lbl_desc_ai)
        controls.addStretch(1)

        vdesc.addWidget(seed_box)
        vdesc.addLayout(controls)
        vdesc.addWidget(gen_box, 1)
        self.sections_tabs.addTab(w_desc, "Description")

        # Videos: table of video src (UI name; HTML id is 'simulation')
        self.sim_table = self._make_table(["Video URL"])
        self.sim_table.cellChanged.connect(lambda *_: self._on_any_changed())
        self.sections_tabs.addTab(self._wrap_table_with_buttons(self.sim_table, "video"), "Videos")

        # Schematic: image src/alt + preview
        w_sch = QWidget(); schf = QFormLayout(w_sch); schf.setVerticalSpacing(8)
        self.sch_src = QLineEdit(); self.sch_alt = QLineEdit()
        self.sch_src.setPlaceholderText("../images/xxx_schematic_01.png")
        self.sch_alt.setPlaceholderText("Schematic")
        self.sch_src.textChanged.connect(lambda *_: (self._update_preview('schematic'), self._on_any_changed()))
        self.sch_alt.textChanged.connect(self._on_any_changed)
        schf.addRow("Image src:", self.sch_src); schf.addRow("Alt text:", self.sch_alt)
        self.sch_preview = PreviewLabel()
        schf.addRow("Preview:", self.sch_preview)
        self.sections_tabs.addTab(w_sch, "Schematic")

        # Layout: image src/alt + preview
        w_lay = QWidget(); layf = QFormLayout(w_lay); layf.setVerticalSpacing(8)
        self.lay_src = QLineEdit(); self.lay_alt = QLineEdit()
        self.lay_src.setPlaceholderText("../images/xxx_components_top.png")
        self.lay_alt.setPlaceholderText("Top view of miniPCB")
        self.lay_src.textChanged.connect(lambda *_: (self._update_preview('layout'), self._on_any_changed()))
        self.lay_alt.textChanged.connect(self._on_any_changed)
        layf.addRow("Image src:", self.lay_src); layf.addRow("Alt text:", self.lay_alt)
        self.lay_preview = PreviewLabel()
        layf.addRow("Preview:", self.lay_preview)
        self.sections_tabs.addTab(w_lay, "Layout")

        # Downloads: table text + href
        self.dl_table = self._make_table(["Text", "Href"])
        self.dl_table.cellChanged.connect(lambda *_: self._on_any_changed())
        self.sections_tabs.addTab(self._wrap_table_with_buttons(self.dl_table, "download"), "Downloads")

        # Resources: table of video src
        self.res_table = self._make_table(["Video URL"])
        self.res_table.cellChanged.connect(lambda *_: self._on_any_changed())
        self.sections_tabs.addTab(self._wrap_table_with_buttons(self.res_table, "video"), "Additional Resources")

        # Metadata change detectors
        self.ed_title.textChanged.connect(self._on_any_changed)
        self.ed_keywords.textChanged.connect(self._on_any_changed)
        self.ed_description.textChanged.connect(self._on_any_changed)
        self.ed_h1.textChanged.connect(self._on_any_changed)
        self.ed_slogan.textChanged.connect(self._on_any_changed)

    # ---------- Small UI helpers ----------
    def _make_table(self, headers: List[str]) -> QTableWidget:
        tbl = QTableWidget(0, len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        for c in range(len(headers)):
            mode = QHeaderView.Stretch if len(headers) == 1 or c == len(headers)-1 else QHeaderView.ResizeToContents
            tbl.horizontalHeader().setSectionResizeMode(c, mode)
        return tbl

    def _wrap_table_with_buttons(self, tbl: QTableWidget, noun: str) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0,0,0,0)
        v.addWidget(tbl, 1)
        row = QHBoxLayout()
        b_add = QPushButton(f"Add {noun}"); b_del = QPushButton("Remove Selected")
        b_add.clicked.connect(lambda: (tbl.insertRow(tbl.rowCount()), self._on_any_changed()))
        b_del.clicked.connect(lambda: (tbl.removeRow(tbl.currentRow()) if tbl.currentRow() >= 0 else None, self._on_any_changed()))
        row.addWidget(b_add); row.addWidget(b_del); row.addStretch(1)
        v.addLayout(row)
        return w

    def _install_row_context_menu(self, table: QTableWidget):
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        def show_menu(pos: QPoint):
            r = table.indexAt(pos).row()
            if r < 0: return
            m = QMenu(table)
            a_above = m.addAction("Add row above")
            a_below = m.addAction("Add row below")
            act = m.exec_(table.viewport().mapToGlobal(pos))
            if act == a_above:
                table.insertRow(r)
            elif act == a_below:
                table.insertRow(r+1)
            else:
                return
            self._on_any_changed()
        table.customContextMenuRequested.connect(show_menu)

    # Context menu for collection table (requested)
    def _collection_context_menu(self, pos: QPoint):
        r = self.collection_tbl.indexAt(pos).row()
        if r < 0: return
        m = QMenu(self.collection_tbl)
        a_above = m.addAction("Add row above")
        a_below = m.addAction("Add row below")
        act = m.exec_(self.collection_tbl.viewport().mapToGlobal(pos))
        if act == a_above:
            self.collection_tbl.insertRow(r)
        elif act == a_below:
            self.collection_tbl.insertRow(r+1)
        else:
            return
        self._on_any_changed()

    # ---------- Page mode toggle ----------
    def _switch_page_mode(self, mode: str):
        self.page_mode = "collection" if str(mode).lower().startswith("coll") else "detail"
        if hasattr(self.tabs, "setTabVisible"):
            self.tabs.setTabVisible(self.idx_sections_tab, self.page_mode == "detail")
            self.tabs.setTabVisible(self.idx_collection_tab, self.page_mode == "collection")
        else:
            self.tabs.setTabEnabled(self.idx_sections_tab, self.page_mode == "detail")
            self.tabs.setTabEnabled(self.idx_collection_tab, self.page_mode == "collection")

    # ---------- Selection ----------
    def selected_source_index(self) -> Optional[QModelIndex]:
        sel = self.tree.selectionModel().selectedIndexes()
        if not sel: return None
        idx = sel[0]
        if idx.column()!=0: idx = self.proxy.index(idx.row(), 0, idx.parent())
        return self.proxy.mapToSource(idx)

    def selected_path(self) -> Optional[Path]:
        sidx = self.selected_source_index()
        if not sidx or not sidx.isValid(): return None
        return Path(self.fs_model.filePath(sidx))

    def on_tree_selection(self, *_):
        path = self.selected_path()
        if not path: return
        self._loading = True
        try:
            if path.is_dir():
                self.current_path = None
                self.path_label.setText(f"Folder: {path}")
                self._set_stats(None)
                self._clear_ui()
                self._switch_page_mode("detail")
                self._set_dirty(False)
                return
            if not (path.suffix.lower() in (".html",".htm")):
                self.current_path = None
                self._clear_ui(); self._set_stats(None)
                self._switch_page_mode("detail")
                self._set_dirty(False)
                return

            self.current_path = path
            self.path_label.setText(f"File: {path}")

            try:
                text = path.read_text(encoding="utf-8")
            except Exception as e:
                self._error("Read error", f"Failed to read file:\n{e}")
                return

            text = ascii_sanitize(text)
            self._clear_ui()
            self.review_raw.setPlainText(text)
            self._review_dirty = False

            if BS4_AVAILABLE:
                soup = BeautifulSoup(text, "html.parser")
                is_detail = bool(soup.find("div", class_="tab-container"))
                if is_detail:
                    self._switch_page_mode("detail")
                    self._load_detail_from_soup(soup)
                else:
                    self._switch_page_mode("collection")
                    self._load_collection_page_from_soup(soup)
                # in both cases, load nav
                self._load_nav_from_soup(soup)
            else:
                self._switch_page_mode("detail")

            self._set_stats(path)
            self._update_preview('schematic')
            self._update_preview('layout')
            self._set_dirty(False)
        finally:
            self._loading = False

    # ---------- UI population (Detail pages) ----------
    def _clear_ui(self):
        self.ed_title.clear()
        self.ed_keywords.clear()
        self.ed_description.clear()
        self.ed_h1.clear()
        self.ed_slogan.clear()
        for ed in (getattr(self, 'det_part', None), getattr(self, 'det_title', None), getattr(self, 'det_board', None),
                   getattr(self, 'det_pieces', None), getattr(self, 'det_panel', None),
                   getattr(self, 'sch_src', None), getattr(self, 'sch_alt', None),
                   getattr(self, 'lay_src', None), getattr(self, 'lay_alt', None)):
            if isinstance(ed, QLineEdit): ed.clear()
        for tbl in (getattr(self, 'sim_table', None), getattr(self, 'dl_table', None), getattr(self, 'res_table', None),
                    getattr(self, 'nav_table', None), getattr(self, 'collection_tbl', None)):
            if isinstance(tbl, QTableWidget):
                tbl.blockSignals(True); tbl.setRowCount(0); tbl.blockSignals(False)
        if hasattr(self, "sch_preview"): self.sch_preview.set_pixmap(None)
        if hasattr(self, "lay_preview"): self.lay_preview.set_pixmap(None)
        if hasattr(self, "desc_seed"): self.desc_seed.blockSignals(True); self.desc_seed.clear(); self.desc_seed.blockSignals(False)
        if hasattr(self, "desc_generated"): self.desc_generated.clear()
        self._desc_generated_raw = ""
        self.review_raw.blockSignals(True); self.review_raw.clear(); self.review_raw.blockSignals(False)
        self._review_dirty = False
        self._set_ai_status_idle()

    def _load_detail_from_soup(self, soup: BeautifulSoup):
        # Metadata
        title = (soup.title.string if soup.title and soup.title.string else "") if soup.title else ""
        self.ed_title.setText((title or "").strip())
        kw = soup.find("meta", attrs={"name":"keywords"})
        self.ed_keywords.setPlainText(kw["content"].strip() if kw and kw.has_attr("content") else "")
        desc = soup.find("meta", attrs={"name":"description"})
        self.ed_description.setPlainText(desc["content"].strip() if desc and desc.has_attr("content") else "")
        h1 = soup.find("h1"); self.ed_h1.setText(h1.get_text(strip=True) if h1 else "")
        slog = soup.find("p", class_="slogan"); self.ed_slogan.setText(slog.get_text(strip=True) if slog else "")

        # Details (robustly strip label + optional colon)
        details = soup.find("div", class_="tab-content", id="details")
        def _get_detail(label: str) -> str:
            if not details: return ""
            for p in details.find_all("p"):
                strong = p.find("strong")
                if not strong: continue
                if strong.get_text(strip=True).rstrip(":").lower() != label.lower():
                    continue
                label_text = strong.get_text(" ", strip=True)
                full = p.get_text(" ", strip=True)
                pattern = rf"^{re.escape(label_text.rstrip(':'))}\s*:?\s*"
                return re.sub(pattern, "", full, flags=re.I)
            return ""
        self.det_part.setText(_get_detail("Part No"))
        self.det_title.setText(_get_detail("Title"))
        self.det_board.setText(_get_detail("Board Size"))
        self.det_pieces.setText(_get_detail("Pieces per Panel"))
        self.det_panel.setText(_get_detail("Panel Size"))

        # Description (seed + generated)
        desc_div = soup.find("div", class_="tab-content", id="description")
        seed_text = ""
        gen_html = ""
        if desc_div:
            for h3 in desc_div.find_all(["h3","h4"]):
                t = h3.get_text(strip=True).lower()
                if "seed" in t:
                    cur = h3.find_next_sibling()
                    while cur and getattr(cur, "name", None) in (None,):
                        cur = cur.next_sibling
                    if cur and getattr(cur, "name", "") in ("p","div","section"):
                        seed_text = cur.get_text("\n", strip=True)
                if "ai generated" in t or t == "ai":
                    gen_block = h3.find_next_sibling()
                    while gen_block and getattr(gen_block, "name", None) in (None,):
                        gen_block = gen_block.next_sibling
                    if gen_block and (("generated" in (gen_block.get("class") or [])) or getattr(gen_block, "name", "") in ("div","p","section")):
                        gen_html = gen_block.decode_contents() if hasattr(gen_block, "decode_contents") else "".join(str(x) for x in gen_block.contents)
        self.desc_seed.blockSignals(True)
        self.desc_seed.setPlainText(seed_text or "")
        self.desc_seed.blockSignals(False)
        self.desc_generated.setHtml(gen_html or "")
        self._desc_generated_raw = gen_html or ""

        # Videos (iframes from id="simulation")
        self._populate_iframe_table(self.sim_table, soup.find("div", class_="tab-content", id="simulation"))

        # Schematic image
        sch = soup.find("div", class_="tab-content", id="schematic")
        img = (sch.find("img", class_="zoomable") if sch else None) or (sch.find("img") if sch else None)
        self.sch_src.setText(img.get("src","") if img else "")
        self.sch_alt.setText(img.get("alt","") if img else "")

        # Layout image
        lay = soup.find("div", class_="tab-content", id="layout")
        limg = (lay.find("img", class_="zoomable") if lay else None) or (lay.find("img") if lay else None)
        self.lay_src.setText(limg.get("src","") if limg else "")
        self.lay_alt.setText(limg.get("alt","") if limg else "")

        # Downloads (links)
        dl = soup.find("div", class_="tab-content", id="downloads")
        self.dl_table.blockSignals(True)
        self.dl_table.setRowCount(0)
        if dl:
            for a in dl.find_all("a"):
                r = self.dl_table.rowCount(); self.dl_table.insertRow(r)
                self.dl_table.setItem(r, 0, QTableWidgetItem(a.get_text(strip=True)))
                self.dl_table.setItem(r, 1, QTableWidgetItem(a.get("href","")))
        self.dl_table.blockSignals(False)

        # Resources (iframes)
        self._populate_iframe_table(self.res_table, soup.find("div", class_="tab-content", id="resources"))

    # ---------- UI population (Collection pages) ----------
    def _load_collection_page_from_soup(self, soup: BeautifulSoup):
        # Common metadata also editable
        title = (soup.title.string if soup.title and soup.title.string else "") if soup.title else ""
        self.ed_title.setText((title or "").strip())
        kw = soup.find("meta", attrs={"name":"keywords"})
        self.ed_keywords.setPlainText(kw["content"].strip() if kw and kw.has_attr("content") else "")
        desc = soup.find("meta", attrs={"name":"description"})
        self.ed_description.setPlainText(desc["content"].strip() if desc and desc.has_attr("content") else "")
        h1 = soup.find("h1"); self.ed_h1.setText(h1.get_text(strip=True) if h1 else "")
        slog = soup.find("p", class_="slogan"); self.ed_slogan.setText(slog.get_text(strip=True) if slog else "")

        # Parse first table under <main> (or anywhere)
        self.collection_tbl.blockSignals(True)
        self.collection_tbl.setRowCount(0)
        tbl = None
        main = soup.find("main")
        if main: tbl = main.find("table")
        if not tbl: tbl = soup.find("table")
        if tbl:
            tbody = tbl.find("tbody") or tbl
            for tr in tbody.find_all("tr"):
                tds = tr.find_all(["td","th"])
                if not tds: continue
                part_no = tds[0].get_text(strip=True) if len(tds) >= 1 else ""
                title_text, href = "", ""
                if len(tds) >= 2:
                    a = tds[1].find("a")
                    if a:
                        title_text = a.get_text(strip=True)
                        href = a.get("href","")
                    else:
                        title_text = tds[1].get_text(strip=True)
                        href = ""
                pieces = tds[2].get_text(strip=True) if len(tds) >= 3 else ""
                r = self.collection_tbl.rowCount(); self.collection_tbl.insertRow(r)
                self.collection_tbl.setItem(r, 0, QTableWidgetItem(part_no))
                self.collection_tbl.setItem(r, 1, QTableWidgetItem(title_text))
                self.collection_tbl.setItem(r, 2, QTableWidgetItem(href))
                self.collection_tbl.setItem(r, 3, QTableWidgetItem(pieces))
        self.collection_tbl.blockSignals(False)

    # ---------- Navigation: load & save ----------
    def _load_nav_from_soup(self, soup: BeautifulSoup):
        self.nav_table.blockSignals(True)
        self.nav_table.setRowCount(0)
        nav = soup.find("nav")
        if nav:
            ul = nav.find("ul", class_="nav-links") or nav.find("ul")
            if ul:
                for li in ul.find_all("li", recursive=False):
                    a = li.find("a")
                    if not a: continue
                    label = a.get_text(strip=True)
                    href = a.get("href","")
                    r = self.nav_table.rowCount(); self.nav_table.insertRow(r)
                    self.nav_table.setItem(r, 0, QTableWidgetItem(label))
                    self.nav_table.setItem(r, 1, QTableWidgetItem(href))
        self.nav_table.blockSignals(False)

    def _save_nav_into_soup(self, soup: BeautifulSoup):
        nav = soup.find("nav")
        if not nav:
            nav = soup.new_tag("nav")
            (soup.body or soup).insert(0, nav)
        container = nav.find("div", class_="nav-container")
        if not container:
            container = soup.new_tag("div", **{"class":"nav-container"})
            nav.append(container)
        ul = container.find("ul", class_="nav-links")
        if not ul:
            ul = soup.new_tag("ul", **{"class":"nav-links"})
            container.append(ul)
        # clear and rebuild
        for child in list(ul.children):
            child.decompose()
        for r in range(self.nav_table.rowCount()):
            label = self.nav_table.item(r,0).text().strip() if self.nav_table.item(r,0) else ""
            href = self.nav_table.item(r,1).text().strip() if self.nav_table.item(r,1) else ""
            if not (label or href): continue
            li = soup.new_tag("li")
            a = soup.new_tag("a", href=(href or "#"))
            a.string = label or href
            li.append(a); ul.append(li)

    # ---------- Common helpers (iframes, tables) ----------
    def _populate_iframe_table(self, table: QTableWidget, container):
        table.blockSignals(True)
        table.setRowCount(0)
        if container:
            for ifr in container.find_all("iframe"):
                src = ifr.get("src","").strip()
                r = table.rowCount(); table.insertRow(r)
                self._set_table_item(table, r, 0, src)
        table.blockSignals(False)

    @staticmethod
    def _set_table_item(tbl, r, c, value):
        it = tbl.item(r, c)
        if it is None:
            it = QTableWidgetItem(value)
            tbl.setItem(r, c, it)
        else:
            it.setText(value)

    def _table_to_list(self, tbl: QTableWidget) -> List[str]:
        vals = []
        for r in range(tbl.rowCount()):
            it = tbl.item(r, 0)
            v = (it.text().strip() if it else "")
            if v: vals.append(v)
        return vals

    def _iter_download_rows(self):
        for r in range(self.dl_table.rowCount()):
            t = self.dl_table.item(r,0).text().strip() if self.dl_table.item(r,0) else ""
            h = self.dl_table.item(r,1).text().strip() if self.dl_table.item(r,1) else ""
            yield t, h

    def _write_iframe_list(self, soup: BeautifulSoup, container, urls: List[str], heading_kept=True):
        for url in urls:
            wrap = soup.new_tag("div", **{"class":"video-wrapper"})
            ifr = soup.new_tag("iframe", **{
                "width":"560", "height":"315", "src":url,
                "title":"YouTube video player", "frameborder":"0",
                "allow":"accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share",
                "allowfullscreen": True, "referrerpolicy":"strict-origin-when-cross-origin"
            })
            wrap.append(ifr); container.append(wrap)

    # ---------- Image previews ----------
    def _resolve_img_path(self, src: str) -> Optional[Path]:
        if not src or not self.current_path: return None
        u = urlparse(src)
        if u.scheme in ("http","https","data"): return None
        raw = unquote(u.path)
        p = Path(raw)
        if p.is_absolute(): return p if p.exists() else None
        candidate = (self.current_path.parent / p).resolve()
        return candidate if candidate.exists() else None

    def _update_preview(self, kind: str):
        if kind == 'schematic':
            src = self.sch_src.text().strip()
            lbl = self.sch_preview
        else:
            src = self.lay_src.text().strip()
            lbl = self.lay_preview
        path = self._resolve_img_path(src)
        if path and path.exists():
            pm = QPixmap(str(path))
            lbl.set_pixmap(pm if not pm.isNull() else None)
        else:
            lbl.set_pixmap(None)

    # ---------- Save ----------
    def save_from_form(self, silent: bool=False):
        if not self.current_path or not self.current_path.exists():
            if not silent: self._info("Save", "Select an HTML file first.")
            return

        # Raw writer wins if edited
        if self._review_dirty:
            text = ascii_sanitize(self.review_raw.toPlainText())
            try:
                tmp = self.current_path.with_suffix(self.current_path.suffix + f".tmp.{os.getpid()}.{now_stamp()}")
                tmp.write_text(text, encoding="utf-8")
                os.replace(str(tmp), str(self.current_path))
                self._review_dirty = False
                self._set_stats(self.current_path)
                self.proxy.refresh_desc(self.current_path)
                self._set_dirty(False)
            except Exception as e:
                try:
                    if 'tmp' in locals() and tmp.exists(): tmp.unlink()
                except Exception:
                    pass
                if not silent: self._error("Save error", f"Failed to save:\n{e}")
            return

        if not BS4_AVAILABLE:
            if not silent:
                self._warn("BeautifulSoup required",
                           "Structured save requires BeautifulSoup.\nInstall with:\n\n    pip install beautifulsoup4\n\n"
                           "Or switch to the Review tab and save raw HTML.")
            return

        # Parse current HTML
        try:
            raw = self.current_path.read_text(encoding="utf-8")
        except Exception as e:
            if not silent: self._error("Read error", f"Failed to read file:\n{e}")
            return

        soup = BeautifulSoup(raw, "html.parser")

        # --- Update common metadata
        self._upsert_metadata_into_soup(soup)
        # --- Update navigation (both modes)
        self._save_nav_into_soup(soup)

        # --- Branch by page mode
        if self.page_mode == "collection":
            self._save_collection_into_soup(soup)
            self._remove_detail_scripts_and_lightbox(soup)
        else:
            self._save_detail_into_soup(soup)

        out_txt = ascii_sanitize(compact_html_for_readability(soup))
        try:
            tmp = self.current_path.with_suffix(self.current_path.suffix + f".tmp.{os.getpid()}.{now_stamp()}")
            tmp.write_text(out_txt, encoding="utf-8")
            os.replace(str(tmp), str(self.current_path))
        except Exception as e:
            try:
                if 'tmp' in locals() and tmp.exists(): tmp.unlink()
            except Exception:
                pass
            if not silent: self._error("Save error", f"Failed to save:\n{e}")
            return

        self._set_stats(self.current_path)
        self.proxy.refresh_desc(self.current_path)
        self._set_dirty(False)

    # ---------- Save helpers (common) ----------
    def _upsert_metadata_into_soup(self, soup: BeautifulSoup):
        # <title>
        new_title = self.ed_title.text().strip()
        if soup.title:
            if soup.title.string: soup.title.string.replace_with(new_title)
            else: soup.title.string = new_title
        else:
            if not soup.head:
                if not soup.html: soup.append(soup.new_tag("html"))
                soup.html.insert(0, soup.new_tag("head"))
            t = soup.new_tag("title"); t.string = new_title
            soup.head.append(t)

        # meta keywords/description
        def upsert_meta(name: str, value: str):
            tag = soup.find("meta", attrs={"name": name})
            if tag is None:
                tag = soup.new_tag("meta")
                tag.attrs["name"] = name
                if not soup.head:
                    if not soup.html: soup.append(soup.new_tag("html"))
                    soup.html.insert(0, soup.new_tag("head"))
                soup.head.append(tag)
            tag.attrs["content"] = value

        upsert_meta("keywords", condense_meta(self.ed_keywords.toPlainText()))
        upsert_meta("description", condense_meta(self.ed_description.toPlainText()))

        # First <h1>
        new_h1 = self.ed_h1.text().strip()
        h1 = soup.find("h1")
        if h1: h1.clear(); h1.append(new_h1)
        else:
            parent = soup.find("main") or soup.body or soup.html
            if parent:
                nh = soup.new_tag("h1"); nh.string = new_h1
                if parent.contents: parent.insert(0, nh)
                else: parent.append(nh)

        # <p class="slogan">
        new_slogan = self.ed_slogan.text().strip()
        slog = soup.find("p", class_="slogan")
        if slog: slog.clear(); slog.append(new_slogan)
        else:
            parent = soup.find("header") or soup.body or soup.html
            if parent:
                ps = soup.new_tag("p", **{"class":"slogan"}); ps.string = new_slogan
                parent.append(ps)

    # ---------- Save helpers (Detail pages) ----------
    def _ensure_section(self, soup: BeautifulSoup, sec_id: str, heading_text: str):
        main = soup.find("main")
        if not main:
            main = soup.new_tag("main")
            (soup.body or soup).append(main)
        tc = main.find("div", class_="tab-container")
        if not tc:
            tc = soup.new_tag("div", **{"class":"tab-container"})
            main.append(tc)
        tabs_div = tc.find("div", class_="tabs")
        if not tabs_div:
            tabs_div = soup.new_tag("div", **{"class":"tabs"})
            tc.insert(0, tabs_div)
        div = tc.find("div", id=sec_id, class_="tab-content")
        if not div:
            div = soup.new_tag("div", **{"class":"tab-content", "id":sec_id})
            tc.append(div)
        h2 = None
        for ch in div.children:
            if getattr(ch, "name", None) == "h2": h2 = ch; break
        if not h2:
            h2 = soup.new_tag("h2"); h2.string = heading_text
            div.insert(0, h2)
        else:
            h2.string = heading_text
        return div, tabs_div, tc

    def _order_detail_sections(self, soup: BeautifulSoup):
        desired = [
            ("details", "Details"),
            ("description", "Description"),
            ("simulation", "Videos"),
            ("schematic", "Schematic"),
            ("layout", "Layout"),
            ("downloads", "Downloads"),
            ("resources", "Additional Resources"),
        ]
        main = soup.find("main")
        if not main: return
        tc = main.find("div", class_="tab-container")
        if not tc: return
        tabs_div = tc.find("div", class_="tabs")
        if not tabs_div: return

        # Rebuild buttons in desired order
        tabs_div.clear()
        for sec_id, label in desired:
            btn = soup.new_tag("button", **{"class":"tab"})
            btn.attrs["onclick"] = f"showTab('{sec_id}', this)"
            btn.string = label
            tabs_div.append(btn)
        # Active on schematic by default
        for btn in tabs_div.find_all("button"):
            btn["class"] = "tab"
        for btn in tabs_div.find_all("button"):
            if btn.get_text(strip=True).lower() == "schematic":
                btn["class"] = "tab active"; break

        # Reorder contents
        id_to_block = {div.get("id"): div for div in tc.find_all("div", class_="tab-content", recursive=False)}
        first_active_set = False
        for sec_id, _ in desired:
            blk = id_to_block.get(sec_id)
            if blk:
                tc.append(blk)
                if sec_id == "schematic" and not first_active_set:
                    for c in tc.find_all("div", class_="tab-content", recursive=False):
                        c["class"] = "tab-content"
                    blk["class"] = "tab-content active"
                    first_active_set = True

    def _save_detail_into_soup(self, soup: BeautifulSoup):
        # ----- Details -----
        det_div, _, _ = self._ensure_section(soup, "details", "PCB Details")
        for node in list(det_div.find_all(recursive=False))[1:]:
            node.decompose()
        def mk_detail(label: str, value: str):
            p = soup.new_tag("p")
            strong = soup.new_tag("strong"); strong.string = f"{label}:"
            p.append(strong); p.append(" " + value)
            return p
        det_div.append(mk_detail("Part No", self.det_part.text().strip()))
        det_div.append(mk_detail("Title", self.det_title.text().strip()))
        det_div.append(mk_detail("Board Size", self.det_board.text().strip()))
        det_div.append(mk_detail("Pieces per Panel", self.det_pieces.text().strip()))
        det_div.append(mk_detail("Panel Size", self.det_panel.text().strip()))

        # ----- Description (seed + generated) -----
        dsc_div, _, _ = self._ensure_section(soup, "description", "Description")
        for node in list(dsc_div.find_all(recursive=False))[1:]:
            node.decompose()
        h3s = soup.new_tag("h3"); h3s.string = "AI Seed"; dsc_div.append(h3s)
        pseed = soup.new_tag("p"); pseed.string = self.desc_seed.toPlainText().strip(); dsc_div.append(pseed)
        h3g = soup.new_tag("h3"); h3g.string = "AI Generated"; dsc_div.append(h3g)
        wrap = soup.new_tag("div", **{"class":"generated"})
        frag = (self._desc_generated_raw or "").strip()
        if frag:
            try:
                inner = BeautifulSoup(frag, "html.parser")
                body = inner.find("body")
                nodes = body.contents if body else inner.contents
                for node in nodes:
                    wrap.append(node if isinstance(node, str) else node)
            except Exception:
                p = soup.new_tag("p"); p.string = re.sub(r"<[^>]+>", "", frag); wrap.append(p)
        dsc_div.append(wrap)

        # ----- Videos -----
        sim_div, _, _ = self._ensure_section(soup, "simulation", "Videos")
        for node in list(sim_div.find_all(recursive=False))[1:]:
            node.decompose()
        self._write_iframe_list(soup, sim_div, self._table_to_list(self.sim_table))

        # ----- Schematic -----
        sch_div, _, _ = self._ensure_section(soup, "schematic", "Schematic")
        for node in list(sch_div.find_all(recursive=False))[1:]:
            node.decompose()
        lb = soup.new_tag("div", **{"class":"lightbox-container"})
        img = soup.new_tag("img", **{
            "class": "zoomable",
            "src": self.sch_src.text().strip(),
            "alt": self.sch_alt.text().strip() or "Schematic",
        })
        img.attrs["onclick"] = "openLightbox(this)"
        lb.append(img); sch_div.append(lb)

        # ----- Layout -----
        lay_div, _, _ = self._ensure_section(soup, "layout", "Layout")
        for node in list(lay_div.find_all(recursive=False))[1:]:
            node.decompose()
        limg = soup.new_tag("img", **{
            "class": "zoomable",
            "src": self.lay_src.text().strip(),
            "alt": self.lay_alt.text().strip() or "Top view of miniPCB",
        })
        limg.attrs["onclick"] = "openLightbox(this)"
        lay_div.append(limg)

        # ----- Downloads -----
        dl_div, _, _ = self._ensure_section(soup, "downloads", "Downloads")
        for node in list(dl_div.find_all(recursive=False))[1:]:
            node.decompose()
        ul = soup.new_tag("ul", **{"class":"download-list"})
        for text, href in self._iter_download_rows():
            if not (text or href): continue
            li = soup.new_tag("li")
            a = soup.new_tag("a", href=href or "#", target="_blank", rel="noopener"); a.string = text or href or "Download"
            li.append(a); ul.append(li)
        dl_div.append(ul)

        # ----- Resources -----
        res_div, _, _ = self._ensure_section(soup, "resources", "Additional Resources")
        for node in list(res_div.find_all(recursive=False))[1:]:
            node.decompose()
        self._write_iframe_list(soup, res_div, self._table_to_list(self.res_table))

        # Ensure order
        self._order_detail_sections(soup)

    # ---------- Save helpers (Collection pages) ----------
    def _save_collection_into_soup(self, soup: BeautifulSoup):
        main = soup.find("main")
        if not main:
            main = soup.new_tag("main"); (soup.body or soup).append(main)
        section = main.find("section")
        if not section:
            section = soup.new_tag("section"); main.append(section)

        tbl = section.find("table") or main.find("table")
        if not tbl:
            tbl = soup.new_tag("table"); section.append(tbl)

        # Preserve header if present; else create
        thead = tbl.find("thead")
        if not thead:
            thead = soup.new_tag("thead"); trh = soup.new_tag("tr")
            for name in ("Part No", "Title", "Pieces per Panel"):
                th = soup.new_tag("th"); th.string = name; trh.append(th)
            thead.append(trh); tbl.append(thead)

        # Rebuild tbody only
        old_tbody = tbl.find("tbody")
        if old_tbody: old_tbody.decompose()
        tbody = soup.new_tag("tbody")
        for r in range(self.collection_tbl.rowCount()):
            part = (self.collection_tbl.item(r,0).text().strip() if self.collection_tbl.item(r,0) else "")
            title_text = (self.collection_tbl.item(r,1).text().strip() if self.collection_tbl.item(r,1) else "")
            href = (self.collection_tbl.item(r,2).text().strip() if self.collection_tbl.item(r,2) else "")
            pieces = (self.collection_tbl.item(r,3).text().strip() if self.collection_tbl.item(r,3) else "")
            if not (part or title_text or href or pieces):
                continue
            tr = soup.new_tag("tr")
            td_part = soup.new_tag("td"); td_part.string = part; tr.append(td_part)
            td_title = soup.new_tag("td")
            if title_text or href:
                a = soup.new_tag("a", href=(href or "#"))
                a.string = title_text or href
                td_title.append(a)
            tr.append(td_title)
            td_pieces = soup.new_tag("td"); td_pieces.string = pieces; tr.append(td_pieces)
            tbody.append(tr)
        tbl.append(tbody)

    # ---------- Scripts/lightbox cleanup for collections ----------
    def _remove_detail_scripts_and_lightbox(self, soup: BeautifulSoup):
        # Global lightbox div
        lb = soup.find("div", id="lightbox")
        if lb: lb.decompose()
        # Remove tab/lightbox scripts by signature
        for s in list(soup.find_all("script")):
            s_text = (s.string or "") + " ".join(s.stripped_strings)
            if any(sig in s_text for sig in ("showTab(", "openLightbox(", "closeLightbox()", ".tabs .tab")):
                s.decompose()

    # ---------- New-file helpers (nav candidates) ----------
    def _detect_collection_page(self, soup: BeautifulSoup) -> bool:
        is_detail = bool(soup.find("div", class_="tab-container"))
        if is_detail: return False
        return bool(soup.find("table"))

    def _find_collection_candidates(self, base_dir: Path) -> List[Tuple[str,str,Path]]:
        cands: List[Tuple[str,str,Path]] = []
        max_files = 2000
        count = 0
        for root, dirs, files in os.walk(self.content_root):
            for fn in files:
                if not fn.lower().endswith((".html",".htm")): continue
                path = Path(root) / fn
                count += 1
                if count > max_files: break
                try:
                    txt = path.read_text(encoding="utf-8", errors="ignore")
                    if not BS4_AVAILABLE:
                        continue
                    soup = BeautifulSoup(txt, "html.parser")
                    if not self._detect_collection_page(soup):
                        continue
                    label = None
                    h1 = soup.find("h1")
                    if h1 and h1.get_text(strip=True): label = h1.get_text(strip=True)
                    if not label and soup.title and soup.title.string: label = soup.title.string.strip()
                    if not label: label = path.stem
                    href = "/" + str(path.relative_to(self.content_root).as_posix())
                    cands.append((label, href, path))
                except Exception:
                    continue
        # Sort: prefer same-folder first
        def key(x):
            label, href, p = x
            return (0 if p.parent.resolve()==base_dir.resolve() else 1, href.lower())
        cands.sort(key=key)
        return cands

    # ---------- Settings ----------
    def open_settings_dialog(self):
        settings = get_settings()
        cur = settings.value(KEY_CONTENT_DIR, str(default_content_root()))
        dlg = QFileDialog(self)
        dlg.setFileMode(QFileDialog.Directory)
        dlg.setOption(QFileDialog.ShowDirsOnly, True)
        dlg.setWindowTitle("Select Content Root (where your .html live)")
        apply_windows_dark_titlebar(dlg)
        if cur and Path(cur).exists(): dlg.setDirectory(str(cur))
        if dlg.exec_():
            sel = dlg.selectedFiles()
            if sel:
                root = Path(sel[0])
                settings.setValue(KEY_CONTENT_DIR, str(root))
                self.content_root = root
                self.fs_model.setRootPath(str(self.content_root))
                self.tree.setRootIndex(self.proxy.mapFromSource(self.fs_model.index(str(self.content_root))))
                self._info("Content Root set", f"Content root:\n{root}")

    def _set_model(self):
        m, ok = self._ask_text("OpenAI Model", "Model name:", default=self.openai_model)
        if ok and m.strip():
            self.openai_model = m.strip()
            get_settings().setValue(KEY_OPENAI_MODEL, self.openai_model)

    def _set_api_key(self):
        k, ok = self._ask_text("OpenAI API Key", "Paste your OPENAI_API_KEY:", default=(self.openai_key or "sk-"))
        if ok:
            self.openai_key = k.strip()
            get_settings().setValue(KEY_OPENAI_KEY, self.openai_key)

    # ---------- FS actions ----------
    def create_new_folder(self):
        base = self.selected_path() or self.content_root
        if base.is_file(): base = base.parent
        name, ok = self._ask_text("New Folder", "Folder name:")
        if not ok or not name.strip(): return
        target = base / name.strip()
        try:
            target.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            self._warn("Exists", "A file/folder with that name already exists.")
        except Exception as e:
            self._error("Error", f"Failed to create folder:\n{e}")

    def create_new_entry(self):
        base = self.selected_path() or self.content_root
        if base.is_file(): base = base.parent
        name, ok = self._ask_text("New Entry", "File name (without extension):")
        if not ok or not name.strip(): return
        safe = name.strip()
        if not safe.lower().endswith(".html"): safe += ".html"
        target = base / safe
        if target.exists():
            self._warn("Exists", "A file with that name already exists."); return

        # Gather collection candidates for nav
        candidates = self._find_collection_candidates(base)
        nav_pairs: List[Tuple[str,str]] = [("Home", "/index.html")]  # Home always included

        if candidates:
            dlg = NavPickerDialog(self, candidates, base_dir=base)
            apply_windows_dark_titlebar(dlg)
            if dlg.exec_() == dlg.Accepted:
                nav_pairs.extend(dlg.selected_links())
            else:
                # user cancelled → keep only Home
                pass

        # Build nav HTML <li> list from nav_pairs
        nav_li = "\n".join([f'        <li><a href="{href}">{label}</a></li>' for (label, href) in nav_pairs])

        year = datetime.date.today().year
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <!-- Google tag (gtag.js) -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-9ZM2D6XGT2"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', 'G-9ZM2D6XGT2');
  </script>

  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{safe}</title>

  <link rel="icon" type="image/png" href="/favicon.png"/>
  <link rel="stylesheet" href="/styles.css"/>
  <meta name="keywords" content=""/>
  <meta name="description" content=""/>
</head>
<body>
  <nav>
    <div class="nav-container">
      <ul class="nav-links">
{nav_li}
      </ul>
    </div>
  </nav>

  <header>
    <h1>{safe}</h1>
    <p class="slogan"></p>
  </header>

  <main>
    <div class="tab-container">
      <div class="tabs">
        <button class="tab" onclick="showTab('details', this)">Details</button>
        <button class="tab" onclick="showTab('description', this)">Description</button>
        <button class="tab" onclick="showTab('videos', this)">Videos</button>
        <button class="tab active" onclick="showTab('schematic', this)">Schematic</button>
        <button class="tab" onclick="showTab('layout', this)">Layout</button>
        <button class="tab" onclick="showTab('downloads', this)">Downloads</button>
        <button class="tab" onclick="showTab('resources', this)">Additional Resources</button>
      </div>

      <!-- DETAILS TAB -->
      <div id="details" class="tab-content">
        <h2>PCB Details</h2>
        <p><strong>Part No:</strong> </p>
        <p><strong>Title:</strong> </p>
        <p><strong>Board Size:</strong> </p>
        <p><strong>Pieces per Panel:</strong> </p>
        <p><strong>Panel Size:</strong> </p>
      </div>

      <!-- DESCRIPTION TAB -->
      <div id="description" class="tab-content">
        <h2>Description</h2>
        <h3>AI Seed</h3>
        <p></p>
        <h3>AI Generated</h3>
        <div class="generated"></div>
      </div>

      <!-- VIDEOS TAB -->
      <div id="videos" class="tab-content">
        <h2>Videos</h2>
      </div>

      <!-- SCHEMATIC TAB -->
      <div id="schematic" class="tab-content active">
        <h2>Schematic</h2>
        <div class="lightbox-container">
          <img
              src=""
              alt="Schematic"
              class="zoomable"
              onclick="openLightbox(this)"/>
        </div>
      </div>

      <!-- LAYOUT TAB -->
      <div id="layout" class="tab-content">
        <h2>Layout</h2>
        <div class="lightbox-container">
          <img
              src=""
              alt="Top view of miniPCB"
              class="zoomable"
              onclick="openLightbox(this)"/>
        </div>
      </div>

      <!-- DOWNLOADS TAB -->
      <div id="downloads" class="tab-content">
        <h2>Downloads</h2>
        <ul class="download-list"></ul>
      </div>

      <!-- RESOURCES TAB -->
      <div id="resources" class="tab-content">
        <h2>Additional Resources</h2>
      </div>
    </div>
  </main>

  <footer>&copy; {year} miniPCB. All rights reserved.</footer>

  <!-- Global lightbox lives at the end of <body>, not inside a tab -->
  <div id="lightbox" aria-hidden="true" role="dialog" aria-label="Image viewer">
    <img id="lightbox-img" alt="Expanded image"/>
  </div>

  <script>
    // Tabs
    function showTab(id, btn) {{
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tabs .tab').forEach(el => el.classList.remove('active'));
      var pane = document.getElementById(id);
      if (pane) pane.classList.add('active');
      if (btn) btn.classList.add('active');
    }}

    // Lightbox
    const lb = document.getElementById('lightbox');
    const lbImg = document.getElementById('lightbox-img');

    function openLightbox(imgEl) {{
      const src = (imgEl.dataset && imgEl.dataset.full) ? imgEl.dataset.full : imgEl.src;
      lbImg.src = src;
      lb.classList.add('open');
      lb.setAttribute('aria-hidden', 'false');
      document.body.classList.add('no-scroll');
    }}

    function closeLightbox() {{
      lb.classList.remove('open');
      lb.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('no-scroll');
      setTimeout(() => {{ lbImg.src = ''; }}, 150);
    }}

    lb.addEventListener('click', (e) => {{ if (e.target === lb) closeLightbox(); }});
    window.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape' && lb.classList.contains('open')) closeLightbox();
    }});
  </script>
</body>
</html>
"""
        try:
            target.write_text(html, encoding="utf-8")
        except Exception as e:
            self._error("Error", f"Failed to create file:\n{e}")
            return

        sidx = self.fs_model.index(str(target))
        if sidx.isValid():
            pidx = self.proxy.mapFromSource(sidx)
            if pidx.isValid(): self.tree.setCurrentIndex(pidx)

    def rename_item(self):
        path = self.selected_path()
        if not path:
            self._info("Rename", "Select a file or folder to rename.")
            return
        new_name, ok = self._ask_text("Rename", "New name:", default=path.name)
        if not ok or not new_name.strip(): return
        new_path = path.parent / new_name.strip()
        if new_path.exists():
            self._warn("Exists", "Target name already exists."); return
        try:
            path.rename(new_path)
            if self.current_path and self.current_path == path:
                self.current_path = new_path; self.path_label.setText(f"File: {new_path}")
            self.proxy.refresh_desc(new_path)
        except Exception as e:
            self._error("Error", f"Failed to rename:\n{e}")

    def delete_item(self):
        path = self.selected_path()
        if not path: return
        typ = "folder" if path.is_dir() else "file"
        if not self._ask_yes_no("Delete", f"Delete this {typ}?\n{path}"): return
        try:
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink()
            if self.current_path and self.current_path == path:
                self.current_path = None; self._clear_ui(); self._set_stats(None); self.path_label.setText("")
        except Exception as e:
            self._error("Error", f"Failed to delete:\n{e}")

    def open_file_location(self):
        path = self.selected_path()
        if not path:
            self._info("Open Location", "Select a folder or file first.")
            return
        try:
            if platform.system()=="Windows":
                subprocess.run(["explorer", "/select,", str(path.resolve())] if path.is_file() else ["explorer", str(path.resolve())])
            elif platform.system()=="Darwin":
                subprocess.run(["open", "-R", str(path.resolve())] if path.is_file() else ["open", str(path.resolve())])
            else:
                target = str(path.parent.resolve() if path.is_file() else path.resolve())
                subprocess.run(["xdg-open", target])
        except Exception as e:
            self._error("Open Location", f"Failed to open location:\n{e}")

    # ---------- Stats ----------
    def _set_stats(self, path: Optional[Path]):
        if not path or not path.exists():
            self.stat_lines.setText("-"); self.stat_words.setText("-"); self.stat_chars.setText("-"); self.stat_edited.setText("-")
            return
        try:
            txt = path.read_text(encoding="utf-8", errors="ignore")
            lines = txt.count("\n") + (1 if txt and not txt.endswith("\n") else 0)
            words = len(re.findall(r"\S+", txt))
            chars = len(txt)
            mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime).isoformat(sep=" ", timespec="seconds")
            self.stat_lines.setText(str(lines))
            self.stat_words.setText(str(words))
            self.stat_chars.setText(str(chars))
            self.stat_edited.setText(mtime)
        except Exception:
            self.stat_lines.setText("?"); self.stat_words.setText("?"); self.stat_chars.setText("?"); self.stat_edited.setText("?")

    # ---------- Dirty / Autosave ----------
    def _on_any_changed(self):
        if self._loading: return
        self._set_dirty(True)

    def _on_review_changed(self):
        if self._loading: return
        self._review_dirty = True
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool):
        if dirty:
            self._dirty = True
            self.autosave_secs_left = self.autosave_interval
            self.autosave_label.setText(f"Autosave in: {self.autosave_secs_left}s")
            self.path_label.setStyleSheet("color:#4CE06A; font-weight:600;")
        else:
            self._dirty = False
            self.autosave_label.setText("Autosave in: -")
            self.path_label.setStyleSheet("")

    def _autosave_tick(self):
        if not self.current_path:
            self.autosave_label.setText("Autosave in: -")
            return
        if self._dirty:
            self.autosave_secs_left = max(0, self.autosave_secs_left - 1)
            self.autosave_label.setText(f"Autosave in: {self.autosave_secs_left}s")
            if self.autosave_secs_left == 0:
                self.save_from_form(silent=True)
        else:
            self.autosave_label.setText("Autosave in: -")

    # ---------- Description AI: UI/state ----------
    def _start_desc_ai(self):
        if self._ai_running:
            return
        if not OPENAI_AVAILABLE:
            self._warn("OpenAI not installed", "Install with:\n\n    pip install openai\n")
            return
        if not self.openai_key:
            self._set_api_key()
            if not self.openai_key:
                self._warn("API key required", "OpenAI API key not set.")
                return

        seed = self.desc_seed.toPlainText().strip()
        page_title = self.ed_title.text().strip()
        h1 = self.ed_h1.text().strip()
        part_no = self.det_part.text().strip()

        self._ai_eta_sec = self._estimate_eta_sec(doc_type="description")
        self._ai_start_ts = datetime.datetime.now()
        self._ai_running = True
        self.btn_desc_generate.setEnabled(False)
        self._update_ai_label(elapsed=0, eta=self._ai_eta_sec, status="running")
        self.ai_timer.start(250)

        self.worker = DescAIWorker(
            api_key=self.openai_key,
            model_name=self.openai_model,
            seed_text=seed,
            page_title=page_title,
            h1=h1,
            part_no=part_no,
            timeout=180
        )
        self.worker.finished.connect(self._on_desc_ai_finished)
        self.worker.start()

    def _set_ai_status_idle(self):
        self._ai_running = False
        self._ai_start_ts = None
        self._ai_eta_sec = None
        self.ai_timer.stop()
        self.lbl_desc_ai.setText("AI: idle")
        self.btn_desc_generate.setEnabled(True)

    def _tick_ai_ui(self):
        if not self._ai_running or not self._ai_start_ts:
            return
        elapsed = int((datetime.datetime.now() - self._ai_start_ts).total_seconds())
        self._update_ai_label(elapsed=elapsed, eta=self._ai_eta_sec, status="running")

    def _update_ai_label(self, elapsed: int, eta: Optional[int], status: str):
        def fmt(sec: Optional[int]) -> str:
            if sec is None: return "--:--"
            m, s = divmod(max(0, int(sec)), 60)
            return f"{m:02d}:{s:02d}"
        txt = f"AI: {fmt(elapsed)} / ETA ≈ {fmt(eta)}"
        self.lbl_desc_ai.setText(txt)

    def _on_desc_ai_finished(self, result: dict):
        elapsed = int(result.get("elapsed", 0))
        self._update_ai_label(elapsed=elapsed, eta=self._ai_eta_sec, status="done")
        self.ai_timer.stop()
        self._ai_running = False
        self.btn_desc_generate.setEnabled(True)

        ok = result.get("ok", False)
        if not ok:
            self._error("AI Error", result.get("error", "Unknown error"))
            self._record_run(duration_sec=max(1, elapsed), doc_type="description", ok=False)
            return

        html = result.get("html","").strip()
        if html:
            clean = strip_inline_styles_from_fragment(html)
            self._desc_generated_raw = clean
            self.desc_generated.setHtml(clean)
            self._on_any_changed()

        self._record_run(duration_sec=max(1, elapsed), doc_type="description", ok=True)

    # ---------- AI stats persistence (ETA) ----------
    @property
    def _stats_path(self) -> Path:
        return self.content_root / "minipcb_catalog.json"

    def _load_stats(self) -> dict:
        p = self._stats_path
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "version": 1,
            "bin_edges_sec": [15,30,60,120,300,600],
            "overall": {"runs":0,"hist":[0]*7,"ewma_sec":None,"last_durations_sec":[]},
            "by_doc_type": {"description":{"runs":0,"hist":[0]*7,"ewma_sec":None,"last_durations_sec":[]}},
            "updated_at": today_iso()
        }

    def _save_stats(self, data: dict):
        try:
            self._stats_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _bin_index(edges, x):
        for i, edge in enumerate(edges):
            if x <= edge: return i
        return len(edges)

    @staticmethod
    def _percentile(data, p):
        if not data: return None
        d = sorted(data); k = (len(d)-1) * p
        f = int(k); c = min(f+1, len(d)-1)
        if f == c: return d[f]
        return d[f] + (d[c]-d[f]) * (k-f)

    def _estimate_eta_sec(self, doc_type: str) -> int:
        stats = self._load_stats()
        slot = stats.get("by_doc_type", {}).get(doc_type, {})
        recent = slot.get("last_durations_sec", [])
        if len(recent) >= 3:
            med = self._percentile(recent, 0.5)
            if med: return int(round(med))
        ewma = slot.get("ewma_sec")
        if ewma: return int(round(ewma))
        overall_recent = stats.get("overall", {}).get("last_durations_sec", [])
        if len(overall_recent) >= 3:
            med = self._percentile(overall_recent, 0.5)
            if med: return int(round(med))
        return 60  # default ETA

    def _record_run(self, duration_sec: float, doc_type: str, ok: bool=True):
        stats = self._load_stats()
        edges = stats.get("bin_edges_sec", [15,30,60,120,300,600])
        idx = self._bin_index(edges, duration_sec)
        by = stats.setdefault("by_doc_type", {})
        slot = by.setdefault(doc_type, {"runs":0,"hist":[0]*(len(edges)+1),"ewma_sec":None,"last_durations_sec":[]})
        overall = stats.setdefault("overall", {"runs":0,"hist":[0]*(len(edges)+1),"ewma_sec":None,"last_durations_sec":[]})
        slot["runs"] += 1
        if len(slot["hist"]) < len(edges)+1: slot["hist"] += [0]*((len(edges)+1)-len(slot["hist"]))
        slot["hist"][idx] += 1
        lst = slot["last_durations_sec"]; lst.append(int(duration_sec))
        if len(lst) > 50: del lst[:len(lst)-50]
        a = 0.25
        slot["ewma_sec"] = (a * duration_sec + (1-a) * slot["ewma_sec"]) if slot.get("ewma_sec") else duration_sec
        overall["runs"] += 1
        if len(overall["hist"]) < len(edges)+1: overall["hist"] += [0]*((len(edges)+1)-len(overall["hist"]))
        overall["hist"][idx] += 1
        olst = overall["last_durations_sec"]; olst.append(int(duration_sec))
        if len(olst) > 50: del olst[:len(olst)-50]
        overall["ewma_sec"] = (a * duration_sec + (1-a) * overall["ewma_sec"]) if overall.get("ewma_sec") else duration_sec
        stats["updated_at"] = today_iso()
        self._save_stats(stats)

    # ---------- Tabs change: Refresh Review snapshot ----------
    def _on_tabs_changed(self, idx: int):
        rv = getattr(self, "review_tab", None)
        if rv is None: return
        if self.tabs.widget(idx) is rv and not self._review_dirty and BS4_AVAILABLE and self.current_path and self.current_path.exists():
            try:
                raw = self.current_path.read_text(encoding="utf-8")
                soup = BeautifulSoup(raw, "html.parser")

                # Rebuild from current form state:
                self._upsert_metadata_into_soup(soup)
                self._save_nav_into_soup(soup)
                if self.page_mode == "collection":
                    self._save_collection_into_soup(soup)
                    self._remove_detail_scripts_and_lightbox(soup)
                else:
                    self._save_detail_into_soup(soup)

                snapshot = compact_html_for_readability(soup)
                self.review_raw.blockSignals(True)
                self.review_raw.setPlainText(snapshot)
                self.review_raw.blockSignals(False)
            except Exception:
                pass

    # ---------- Part number change handler ----------
    def _on_partno_changed_update_paths(self):
        if self._loading: return
        pn = self.det_part.text().strip()
        if not pn: return
        sch = f"../images/{pn}_schematic_01.png"
        lay = f"../images/{pn}_components_top.png"
        if not self.sch_src.text().strip():
            self.sch_src.setText(sch)
        if not self.lay_src.text().strip():
            self.lay_src.setText(lay)

# ---------- App boot ----------
def ensure_content_root() -> Path:
    settings = get_settings()
    saved = settings.value(KEY_CONTENT_DIR, None)
    if saved and Path(saved).exists():
        return Path(saved)
    root = default_content_root()
    root.mkdir(parents=True, exist_ok=True)
    return root

def main():
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    icon = make_emoji_icon("💠", px=256)
    app.setWindowIcon(icon)

    root = ensure_content_root()
    win = CatalogWindow(root, icon)
    win.show()
    apply_windows_dark_titlebar(win)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
