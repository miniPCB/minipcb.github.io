#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
miniPCB Catalog — PyQt5
- Clean, compact HTML formatter (readable, minimal line wrapping)
- Review tab always renders current unsaved state
- No inline styles in AI output (uses <div class="generated">)
- Navigation tab (Board + Collection) with link picker
- Collection table: right-click Add Row Above/Below
- Update HTML button upgrades file to current template (keeps data)
- PN→image paths fix; Google tag handled; scripts only on board pages
- NEW: Page Components (checkboxes) to show/hide Description, Videos, Downloads, Additional Resources tabs
"""

from __future__ import annotations
import sys, os, re, json, shutil, subprocess, datetime, platform, time
from pathlib import Path
from typing import Optional, Tuple, List
from urllib.parse import urlparse, unquote

# ---- HTML parsing
try:
    from bs4 import BeautifulSoup, Comment, NavigableString, Tag
    BS4_AVAILABLE = True
except Exception:
    BeautifulSoup = None
    Comment = None
    NavigableString = None
    Tag = None
    BS4_AVAILABLE = False

# ---- OpenAI (optional)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except Exception:
    OpenAI = None
    OPENAI_AVAILABLE = False

from PyQt5.QtCore import Qt, QSortFilterProxyModel, QModelIndex, QSettings, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QKeySequence, QIcon, QPixmap, QPainter, QFont, QCursor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFileSystemModel, QTreeView, QToolBar, QAction, QFileDialog,
    QInputDialog, QMessageBox, QLabel, QAbstractItemView, QFormLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QSplitter, QTabWidget, QTextEdit, QStyleFactory, QMenu, QDialog,
    QListWidget, QListWidgetItem, QDialogButtonBox, QCheckBox
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

def make_emoji_icon(emoji: str, px: int = 220) -> QIcon:
    pm = QPixmap(px, px); pm.fill(Qt.transparent)
    p = QPainter(pm)
    try:
        f = QFont("Segoe UI Emoji", int(px * 0.64))
        f.setStyleStrategy(QFont.PreferAntialias); p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignCenter, emoji)
    finally:
        p.end()
    return QIcon(pm)

# ---------- Pretty HTML formatter ----------
VOID_TAGS = {"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}
BLOCK_TAGS = {
    "html","head","body","nav","header","main","footer","section","div",
    "table","thead","tbody","tfoot","tr","th","td","ul","ol","li",
    "h1","h2","h3","h4","h5","h6","p","script","noscript","style",
    "form","button","label","iframe","pre"
}
INLINE_KEEP_ONE_LINE = {"p","li","h1","h2","h3","h4","h5","h6","button","label","a","strong","em","span","code"}
ATTR_ORDER = ["lang","charset","name","content","http-equiv","rel","type","href","src","async","defer","id","class","role","aria-label","title","alt","width","height","target","referrerpolicy","allow","allowfullscreen","frameborder","data-full","onclick","data-hidden"]

def _attrs_sorted(tag: Tag) -> List[Tuple[str, str]]:
    if not isinstance(tag, Tag): return []
    items = list(tag.attrs.items())
    norm = []
    for k, v in items:
        if isinstance(v, list): v = " ".join(v)
        if v is True: v = "True"
        if v is False: v = None
        norm.append((k, v))
    def keypair(it):
        k, _ = it
        idx = ATTR_ORDER.index(k) if k in ATTR_ORDER else 999
        return (idx, k)
    return [(k, v) for (k, v) in sorted(norm, key=keypair) if v is not None]

def _tag_open(tag: Tag) -> str:
    attrs = _attrs_sorted(tag)
    if not attrs: return f"<{tag.name}>"
    parts = [f'{k}="{v}"' if v is not True else k for k, v in attrs]
    return f"<{tag.name} " + " ".join(parts) + ">"

def _tag_selfclose(tag: Tag) -> str:
    attrs = _attrs_sorted(tag)
    if not attrs: return f"<{tag.name}>"
    parts = [f'{k}="{v}"' if v is not True else k for k, v in attrs]
    return f"<{tag.name} " + " ".join(parts) + ">"

def _text_collapse(s: str) -> str:
    s = re.sub(r"[ \t\r\n]+", " ", s)
    return s.strip()

def minipcb_format_html(soup: BeautifulSoup) -> str:
    lines: List[str] = []
    indent = 0
    def write(line=""):
        lines.append(("  " * indent) + line if line else "")
    def emit(node):
        nonlocal indent
        if isinstance(node, Comment):
            write(f"<!--{str(node)}-->"); return
        if isinstance(node, NavigableString):
            txt = _text_collapse(str(node))
            if txt:
                if lines and lines[-1] and not lines[-1].endswith(">"):
                    lines[-1] += txt
                else:
                    write(txt)
            return
        if not isinstance(node, Tag): return
        name = node.name.lower()
        if name in VOID_TAGS:
            write(_tag_selfclose(node)); return
        if name == "script":
            write(_tag_open(node)); indent += 1
            raw = "".join(str(c) for c in node.contents); raw = ascii_sanitize(raw).strip("\n")
            for ln in raw.split("\n"): write(ln.rstrip())
            indent -= 1; write(f"</{name}>"); return
        if name in {"ul","ol","table","thead","tbody","tfoot","tr"}:
            write(_tag_open(node)); indent += 1
            for c in node.contents or []:
                if isinstance(c, NavigableString) and not _text_collapse(str(c)): continue
                emit(c)
            indent -= 1; write(f"</{name}>"); return
        if name in INLINE_KEEP_ONE_LINE and all(
            not isinstance(c, Tag) or c.name in (INLINE_KEEP_ONE_LINE | VOID_TAGS | {"sup","sub","small","br","iframe"})
            for c in node.contents or []
        ):
            open_tag = _tag_open(node)[:-1]
            buf = []
            for c in node.contents or []:
                if isinstance(c, NavigableString):
                    buf.append(_text_collapse(str(c)))
                elif isinstance(c, Tag):
                    if c.name in VOID_TAGS: buf.append(_tag_selfclose(c))
                    else:
                        inner = "".join(_text_collapse(str(x)) if isinstance(x, NavigableString) else str(x) for x in c.contents or [])
                        buf.append(_tag_open(c)[:-1] + ">" + inner + f"</{c.name}>")
            write(open_tag + ">" + " ".join([t for t in buf if t]) + f"</{name}>"); return
        write(_tag_open(node)); indent += 1
        for c in node.contents or []:
            if isinstance(c, NavigableString) and not _text_collapse(str(c)): continue
            emit(c)
        indent -= 1; write(f"</{name}>")
    out = str(soup); has_doctype = out.lower().lstrip().startswith("<!doctype html>")
    if not has_doctype: lines.append("<!DOCTYPE html>")
    if hasattr(soup, "html") and soup.html: emit(soup.html)
    else:
        for c in soup.contents: emit(c)
    return "\n".join(lines).rstrip() + "\n"

# ---------- AI Worker ----------
class DescAIWorker(QThread):
    finished = pyqtSignal(dict)
    def __init__(self, api_key: str, model_name: str, seed_text: str, page_title: str, h1: str, part_no: str, timeout: int = 120):
        super().__init__()
        self.api_key = api_key; self.model = model_name; self.seed = seed_text or ""
        self.page_title = page_title or ""; self.h1 = h1 or ""; self.part_no = part_no or ""; self.timeout = timeout
    def run(self):
        start = time.time()
        try:
            if not OPENAI_AVAILABLE: raise RuntimeError("OpenAI SDK not installed. pip install openai")
            if not self.api_key: raise RuntimeError("OPENAI_API_KEY not set.")
            client = OpenAI(api_key=self.api_key)
            sys_prompt = ("You are an expert technical copywriter for a hardware mini PCB catalog.\n"
                          "Write crisp, accurate, helpful product descriptions. Return ONLY an HTML fragment (p/ul/li/h3 ok).")
            user_prompt = (
                f"PAGE CONTEXT:\n- Page Title: {self.page_title}\n- H1: {self.h1}\n- Part No: {self.part_no}\n\n"
                f"SEED:\n{self.seed}\n\n"
                "TASK:\n• 2–4 short paragraphs + (optional) ONE bullet list (3–6 items).\n"
                "• 180–260 words; neutral, technical; no marketing fluff.\n"
                "• Output ONLY an HTML fragment; no <html>/<body>; no inline styles."
            )
            html = ""
            try:
                resp = client.responses.create(model=self.model,
                                               input=[{"role":"system","content":sys_prompt},{"role":"user","content":user_prompt}],
                                               timeout=self.timeout)
                html = getattr(resp, "output_text", None) or ""
                if not html:
                    try: html = resp.output[0].content[0].text
                    except Exception: html = ""
            except Exception:
                cc = client.chat.completions.create(model=self.model,
                                                    messages=[{"role":"system","content":sys_prompt},{"role":"user","content":user_prompt}],
                                                    timeout=self.timeout)
                try: html = cc.choices[0].message.content or ""
                except Exception: html = ""
            if not html: raise RuntimeError("Model returned empty content.")
            elapsed = time.time() - start; self.finished.emit({"ok": True, "html": html.strip(), "elapsed": elapsed})
        except Exception as e:
            elapsed = time.time() - start; self.finished.emit({"ok": False, "error": str(e), "elapsed": elapsed})

# ---------- Preview label ----------
class PreviewLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent); self._pix: Optional[QPixmap] = None
        self.setMinimumHeight(220); self.setAlignment(Qt.AlignCenter); self.setText("(no image)")
        self.setStyleSheet("QLabel { border:1px solid #3A3F44; border-radius:6px; padding:6px; }")
    def set_pixmap(self, pix: Optional[QPixmap]):
        self._pix = pix; self._render()
    def resizeEvent(self, e):
        super().resizeEvent(e); self._render()
    def _render(self):
        if not self._pix or self._pix.isNull():
            self.setText("(no image)"); self.setPixmap(QPixmap()); return
        w = max(64, self.width() - 12); h = max(64, self.height() - 12)
        scaled = self._pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled); self.setText("")

# ---------- FS proxy ----------
class DescProxyModel(QSortFilterProxyModel):
    def filterAcceptsRow(self, source_row, source_parent):
        sm = self.sourceModel(); idx = sm.index(source_row, 0, source_parent)
        if not idx.isValid(): return False
        if sm.isDir(idx): return True
        name = sm.fileName(idx).lower()
        return name.endswith(".html") or name.endswith(".htm")
    def columnCount(self, parent): return max(2, super().columnCount(parent))
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        if index.column() == 0: return super().data(index, role)
        if index.column() == 1 and role in (Qt.DisplayRole, Qt.ToolTipRole):
            sidx = self.mapToSource(index.sibling(index.row(), 0)); path = Path(self.sourceModel().filePath(sidx))
            try:
                txt = path.read_text(encoding="utf-8", errors="ignore")
                if BS4_AVAILABLE:
                    soup = BeautifulSoup(txt, "html.parser"); 
                    return (soup.title.string.strip() if soup.title and soup.title.string else "")
                m = re.search(r"<title>(.*?)</title>", txt, re.I | re.S); 
                return (m.group(1).strip() if m else "")
            except Exception: return ""
        if index.column() >= 2 and role == Qt.DisplayRole: return ""
        return super().data(index, role)
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return ["Name", "Title"][section] if section in (0, 1) else super().headerData(section, orientation, role)
        return super().headerData(section, orientation, role)

# ---------- Link picker dialog ----------
class LinkPickerDialog(QDialog):
    def __init__(self, parent, content_root: Path, current_dir: Path):
        super().__init__(parent)
        self.setWindowTitle("Select navigation links"); self.resize(600, 480)
        v = QVBoxLayout(self)
        self.cb_include_parent = QCheckBox("Show only likely collections (folder landing pages)"); self.cb_include_parent.setChecked(True); v.addWidget(self.cb_include_parent)
        self.listw = QListWidget(self); v.addWidget(self.listw, 1)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self); v.addWidget(btns)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        self.content_root = content_root; self.current_dir = current_dir
        self.populate(); self.cb_include_parent.stateChanged.connect(self.populate)
    def populate(self):
        self.listw.clear()
        htmls: List[Path] = []
        for p in self.content_root.rglob("*.html"):
            if p.name.lower() in ("index.html",): continue
            if self.cb_include_parent.isChecked():
                if p.parent.name.lower() == p.stem.lower(): htmls.append(p)
            else:
                htmls.append(p)
        htmls = sorted(set(htmls), key=lambda x: str(x.relative_to(self.content_root)).lower())
        for p in htmls:
            rel = str(p.relative_to(self.content_root)).replace("\\","/")
            item = QListWidgetItem(f"{p.stem} — {rel}"); item.setData(Qt.UserRole, rel); self.listw.addItem(item)
    def selected(self) -> List[str]:
        return [it.data(Qt.UserRole) for it in self.listw.selectedItems()]

# ---------- Main Window ----------
class CatalogWindow(QMainWindow):
    def __init__(self, content_root: Path, app_icon: QIcon):
        super().__init__()
        self.setWindowTitle(APP_TITLE); self.setWindowIcon(app_icon); self.resize(1400, 900)
        self.content_root = content_root; self.current_path: Optional[Path] = None
        self._dirty = False; self._review_dirty = False; self._loading = False

        # OpenAI settings
        s = get_settings()
        self.openai_model = s.value(KEY_OPENAI_MODEL, os.environ.get("OPENAI_MODEL", "gpt-5"))
        self.openai_key = s.value(KEY_OPENAI_KEY, os.environ.get("OPENAI_API_KEY", ""))

        # Autosave
        self.autosave_interval = 30; self.autosave_secs_left = self.autosave_interval
        self.autosave_timer = QTimer(self); self.autosave_timer.timeout.connect(self._autosave_tick); self.autosave_timer.start(1000)

        # AI timers
        self.ai_timer = QTimer(self); self.ai_timer.timeout.connect(self._tick_ai_ui)
        self._ai_start_ts: Optional[datetime.datetime] = None; self._ai_eta_sec: Optional[int] = None; self._ai_running = False

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
        self.act_save.triggered.connect(lambda: self.save_from_form(silent=False)); tb.addAction(self.act_save)
        act_update = QAction("🛠️ Update HTML", self); act_update.triggered.connect(self.update_html_to_template); tb.addAction(act_update)
        tb.addSeparator()
        act_set_model = QAction("🤖 Set Model…", self); act_set_model.triggered.connect(self.open_settings_dialog)
        act_set_key   = QAction("🔑 Set API Key…", self); act_set_key.triggered.connect(self.open_settings_dialog)

        # FS model + tree
        self.fs_model = QFileSystemModel(self); self.fs_model.setReadOnly(False)
        self.fs_model.setRootPath(str(self.content_root))
        self.fs_model.setNameFilters(["*.html", "*.htm"]); self.fs_model.setNameFilterDisables(False)
        self.proxy = DescProxyModel(self); self.proxy.setSourceModel(self.fs_model)
        self.tree = QTreeView(self); self.tree.setModel(self.proxy)
        self.tree.setRootIndex(self.proxy.mapFromSource(self.fs_model.index(str(self.content_root))))
        self.tree.setHeaderHidden(False); self.tree.setSortingEnabled(True); self.tree.sortByColumn(0, Qt.AscendingOrder)
        for col in range(2, self.proxy.columnCount(self.tree.rootIndex())): self.tree.setColumnHidden(col, True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents); self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.selectionModel().selectionChanged.connect(self.on_tree_selection)

        # Right side
        right = QWidget(self); right_v = QVBoxLayout(right); right_v.setContentsMargins(0,0,0,0); right_v.setSpacing(8)
        top_row = QHBoxLayout()
        self.path_label = QLabel("", self)
        self.autosave_label = QLabel("Autosave in: --s", self); self.autosave_label.setStyleSheet("color:#A0E0A0;")
        top_row.addWidget(self.path_label); top_row.addStretch(1); top_row.addWidget(self.autosave_label)
        right_v.addLayout(top_row)

        # Tabs container
        self.tabs = QTabWidget(self)

        # Metadata tab
        self.meta_tab = QWidget(self)
        meta_form = QFormLayout(self.meta_tab); meta_form.setVerticalSpacing(8)
        self.ed_title = QLineEdit(); self.ed_title.setPlaceholderText("<title>…")
        self.ed_keywords = QTextEdit(); self.ed_keywords.setAcceptRichText(False); self.ed_keywords.setMinimumHeight(60)
        self.ed_description = QTextEdit(); self.ed_description.setAcceptRichText(False); self.ed_description.setMinimumHeight(90)
        self.ed_h1 = QLineEdit(); self.ed_slogan = QLineEdit()
        meta_form.addRow("Title:", self.ed_title)
        meta_form.addRow("Meta Keywords:", self.ed_keywords)
        meta_form.addRow("Meta Description:", self.ed_description)
        meta_form.addRow("H1:", self.ed_h1)
        meta_form.addRow("Slogan:", self.ed_slogan)
        self.tabs.addTab(self.meta_tab, "Metadata")

        # Sections host
        self.sections_host = QWidget(self); sh_v = QVBoxLayout(self.sections_host); sh_v.setContentsMargins(0,0,0,0); sh_v.setSpacing(8)

        # NEW: Page Components (checkboxes)
        comp_box = QGroupBox("Page Components"); comp_row = QHBoxLayout(comp_box); comp_row.setSpacing(12)
        self.chk_desc = QCheckBox("Description"); self.chk_videos = QCheckBox("Videos"); self.chk_downloads = QCheckBox("Downloads"); self.chk_resources = QCheckBox("Additional Resources")
        for c in (self.chk_desc, self.chk_videos, self.chk_downloads, self.chk_resources): c.setChecked(True)
        btn_show_all = QPushButton("Show All"); btn_hide_all = QPushButton("Hide All")
        btn_show_all.clicked.connect(lambda: self._set_all_components(True)); btn_hide_all.clicked.connect(lambda: self._set_all_components(False))
        for w in (self.chk_desc, self.chk_videos, self.chk_downloads, self.chk_resources, btn_show_all, btn_hide_all): comp_row.addWidget(w)
        comp_row.addStretch(1)
        for c in (self.chk_desc, self.chk_videos, self.chk_downloads, self.chk_resources):
            c.toggled.connect(self._on_components_changed)
        sh_v.addWidget(comp_box)

        # Sub-tabs (Sections)
        self.sections_tabs = QTabWidget(self.sections_host); sh_v.addWidget(self.sections_tabs, 1)
        self.tabs.addTab(self.sections_host, "Sections")

        # Build the section editors
        self._build_fixed_section_editors()

        # Collection tab
        self.collection_host = QWidget(self); col_v = QVBoxLayout(self.collection_host); col_v.setContentsMargins(0,0,0,0); col_v.setSpacing(8)
        self.collection_tbl = QTableWidget(0, 4)
        self.collection_tbl.setHorizontalHeaderLabels(["Part No", "Title Text", "Href", "Pieces per Panel"])
        self.collection_tbl.verticalHeader().setVisible(False)
        self.collection_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.collection_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.collection_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.collection_tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.collection_tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.collection_tbl.customContextMenuRequested.connect(self._collection_context_menu)
        col_v.addWidget(self.collection_tbl, 1)
        row = QHBoxLayout()
        b_add = QPushButton("Add Row"); b_del = QPushButton("Remove Selected")
        b_add.clicked.connect(lambda: (self.collection_tbl.insertRow(self.collection_tbl.rowCount()), self._on_any_changed()))
        b_del.clicked.connect(lambda: (self.collection_tbl.removeRow(self.collection_tbl.currentRow()) if self.collection_tbl.currentRow()>=0 else None, self._on_any_changed()))
        row.addWidget(b_add); row.addWidget(b_del); row.addStretch(1)
        col_v.addLayout(row)
        self.tabs.addTab(self.collection_host, "Collection")

        # Navigation tab
        self.nav_host = QWidget(self); nv = QVBoxLayout(self.nav_host); nv.setContentsMargins(0,0,0,0)
        self.nav_tbl = QTableWidget(0, 2)
        self.nav_tbl.setHorizontalHeaderLabels(["Text", "Href"])
        self.nav_tbl.verticalHeader().setVisible(False)
        self.nav_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.nav_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        nv.addWidget(self.nav_tbl, 1)
        nrow = QHBoxLayout()
        self.btn_nav_add = QPushButton("Add Link"); self.btn_nav_remove = QPushButton("Remove Selected")
        self.btn_nav_up = QPushButton("Up"); self.btn_nav_down = QPushButton("Down")
        self.btn_nav_add.clicked.connect(self._add_nav_link_via_picker)
        self.btn_nav_remove.clicked.connect(lambda: (self.nav_tbl.removeRow(self.nav_tbl.currentRow()) if self.nav_tbl.currentRow()>=0 else None, self._on_any_changed()))
        self.btn_nav_up.clicked.connect(lambda: self._move_row(self.nav_tbl, -1))
        self.btn_nav_down.clicked.connect(lambda: self._move_row(self.nav_tbl, 1))
        for b in (self.btn_nav_add, self.btn_nav_remove, self.btn_nav_up, self.btn_nav_down): nrow.addWidget(b)
        nrow.addStretch(1); nv.addLayout(nrow)
        self.tabs.addTab(self.nav_host, "Navigation")

        # Review
        self.review_tab = QWidget(self); rv = QVBoxLayout(self.review_tab)
        self.review_raw = QTextEdit(self.review_tab); self.review_raw.setLineWrapMode(QTextEdit.NoWrap)
        self.review_raw.textChanged.connect(self._on_review_changed)
        rv.addWidget(self.review_raw)
        self.tabs.addTab(self.review_tab, "Review")
        self.tabs.currentChanged.connect(self._on_tabs_changed)

        # Stats
        self.stats_tab = QWidget(self); st = QFormLayout(self.stats_tab)
        self.stat_lines = QLabel("-"); self.stat_words = QLabel("-"); self.stat_chars = QLabel("-"); self.stat_edited = QLabel("-")
        st.addRow("Line count:", self.stat_lines); st.addRow("Word count:", self.stat_words)
        st.addRow("Character count:", self.stat_chars); st.addRow("Last edited:", self.stat_edited)
        self.tabs.addTab(self.stats_tab, "Stats")

        right_v.addWidget(self.tabs, 1)

        # Splitter
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self.tree); splitter.addWidget(right)
        splitter.setStretchFactor(0, 1); splitter.setStretchFactor(1, 2); splitter.setSizes([420, 980])
        central = QWidget(self); outer = QHBoxLayout(central); outer.setContentsMargins(8,8,8,8); outer.setSpacing(8); outer.addWidget(splitter); self.setCentralWidget(central)

        self.apply_dark_styles(); apply_windows_dark_titlebar(self)
        self._set_dirty(False)

        if not BS4_AVAILABLE:
            self._info("BeautifulSoup not found", "Install with:\n\n  pip install beautifulsoup4")

    # --- Settings dialog (put this inside CatalogWindow) ---
    def open_settings_dialog(self):
        """Choose the content root folder where your .html files live."""
        settings = get_settings()
        cur = settings.value(KEY_CONTENT_DIR, str(default_content_root()))

        dlg = QFileDialog(self)
        dlg.setFileMode(QFileDialog.Directory)
        dlg.setOption(QFileDialog.ShowDirsOnly, True)
        dlg.setWindowTitle("Select Content Root (where your .html live)")
        apply_windows_dark_titlebar(dlg)
        if cur and Path(cur).exists():
            dlg.setDirectory(str(cur))

        if not dlg.exec_():
            return

        sel = dlg.selectedFiles()
        if not sel:
            return

        root = Path(sel[0])
        settings.setValue(KEY_CONTENT_DIR, str(root))
        self.content_root = root

        # Re-root the file system model and tree
        self.fs_model.setRootPath(str(self.content_root))
        self.tree.setRootIndex(self.proxy.mapFromSource(self.fs_model.index(str(self.content_root))))
        self.path_label.setText(f"Folder: {root}")

    # ---------- Styling ----------
    def apply_dark_styles(self):
        self.setStyleSheet("""
            QWidget { background-color:#202225; color:#E6E6E6; }
            QToolBar { background:#1B1E20; spacing:6px; border:0; }
            QToolButton, QPushButton { color:#E6E6E6; }
            QLabel { color:#E6E6E6; }
            QLineEdit, QTextEdit { background:#2A2D31; color:#E6E6E6; border:1px solid #3A3F44; border-radius:6px; padding:6px; }
            QPushButton { background:#2F343A; border:1px solid #444; border-radius:6px; padding:6px 12px; }
            QPushButton:hover { background:#3A4047; } QPushButton:pressed { background:#2A2F35; }
            QTreeView { background:#1E2124; border:1px solid #3A3F44; }
            QTreeView::item:selected { background:#3B4252; color:#E6E6E6; }
            QHeaderView::section { background:#2A2D31; color:#E6E6E6; border:0; padding:6px; font-weight:600; }
            QTabBar::tab { background:#2A2D31; color:#E6E6E6; padding:8px 12px; margin-right:2px; border-top-left-radius:6px; border-top-right-radius:6px; }
            QTabBar::tab:selected { background:#3A3F44; } QTabBar::tab:hover { background:#34383D; }
            QTableWidget { background:#1E2124; color:#E6E6E6; gridline-color:#3A3F44; border:1px solid #3A3F44; border-radius:6px; }
        """)

    # ---------- UI builders ----------
    def _build_fixed_section_editors(self):
        # Details
        self.w_details = QWidget()
        det_form = QFormLayout(self.w_details); det_form.setVerticalSpacing(8)
        self.det_part = QLineEdit(); self.det_title = QLineEdit(); self.det_board = QLineEdit(); self.det_pieces = QLineEdit(); self.det_panel = QLineEdit()
        det_form.addRow("Part No:", self.det_part); det_form.addRow("Title:", self.det_title); det_form.addRow("Board Size:", self.det_board)
        det_form.addRow("Pieces per Panel:", self.det_pieces); det_form.addRow("Panel Size:", self.det_panel)
        for ed in (self.det_part, self.det_title, self.det_board, self.det_pieces, self.det_panel):
            ed.textChanged.connect(self._on_any_changed)
        self.det_part.textChanged.connect(self._on_part_changed)
        self.sections_tabs.addTab(self.w_details, "Details")

        # Description
        self.w_desc = QWidget(); vdesc = QVBoxLayout(self.w_desc); vdesc.setSpacing(8); vdesc.setContentsMargins(6,6,6,6)
        seed_box = QGroupBox("Seed"); seed_form = QVBoxLayout(seed_box)
        self.desc_seed = QTextEdit(); self.desc_seed.setAcceptRichText(False); self.desc_seed.setMinimumHeight(100)
        self.desc_seed.textChanged.connect(self._on_any_changed); seed_form.addWidget(self.desc_seed)
        gen_box = QGroupBox("AI Generated"); gen_v = QVBoxLayout(gen_box)
        self.desc_generated = QTextEdit(); self.desc_generated.setReadOnly(True); self.desc_generated.setAcceptRichText(True); self.desc_generated.setMinimumHeight(140)
        gen_v.addWidget(self.desc_generated)
        controls = QHBoxLayout(); self.btn_desc_generate = QPushButton("Generate"); self.btn_desc_generate.clicked.connect(self._start_desc_ai)
        self.lbl_desc_ai = QLabel("AI: idle"); self.lbl_desc_ai.setStyleSheet("color:#C8E6C9;")
        controls.addWidget(self.btn_desc_generate); controls.addSpacing(12); controls.addWidget(self.lbl_desc_ai); controls.addStretch(1)
        vdesc.addWidget(seed_box); vdesc.addLayout(controls); vdesc.addWidget(gen_box, 1)
        self.sections_tabs.addTab(self.w_desc, "Description")

        # Videos (id "simulation")
        vids_widget = self._wrap_table_with_buttons(self._make_video_table(), "video")
        self.w_videos = vids_widget
        self.sections_tabs.addTab(self.w_videos, "Videos")

        # Schematic
        self.w_schematic = QWidget(); schf = QFormLayout(self.w_schematic); schf.setVerticalSpacing(8)
        self.sch_src = QLineEdit(); self.sch_alt = QLineEdit()
        self.sch_src.setPlaceholderText("../images/<PN>_schematic_01.png"); self.sch_alt.setPlaceholderText("Schematic")
        self.sch_src.textChanged.connect(lambda *_: (self._update_preview('schematic'), self._on_any_changed()))
        self.sch_alt.textChanged.connect(self._on_any_changed)
        schf.addRow("Image src:", self.sch_src); schf.addRow("Alt text:", self.sch_alt)
        self.sch_preview = PreviewLabel(); schf.addRow("Preview:", self.sch_preview)
        self.sections_tabs.addTab(self.w_schematic, "Schematic")

        # Layout
        self.w_layout = QWidget(); layf = QFormLayout(self.w_layout); layf.setVerticalSpacing(8)
        self.lay_src = QLineEdit(); self.lay_alt = QLineEdit()
        self.lay_src.setPlaceholderText("../images/<PN>_components_top.png"); self.lay_alt.setPlaceholderText("Top view of miniPCB")
        self.lay_src.textChanged.connect(lambda *_: (self._update_preview('layout'), self._on_any_changed()))
        self.lay_alt.textChanged.connect(self._on_any_changed)
        layf.addRow("Image src:", self.lay_src); layf.addRow("Alt text:", self.lay_alt)
        self.lay_preview = PreviewLabel(); layf.addRow("Preview:", self.lay_preview)
        self.sections_tabs.addTab(self.w_layout, "Layout")

        # Downloads
        dls_widget = self._wrap_table_with_buttons(self._make_download_table(), "download")
        self.w_downloads = dls_widget
        self.sections_tabs.addTab(self.w_downloads, "Downloads")

        # Resources
        res_widget = self._wrap_table_with_buttons(self._make_resources_table(), "video")
        self.w_resources = res_widget
        self.sections_tabs.addTab(self.w_resources, "Additional Resources")

    def _make_video_table(self) -> QTableWidget:
        self.sim_table = QTableWidget(0, 1)
        self.sim_table.setHorizontalHeaderLabels(["Video URL"])
        self.sim_table.verticalHeader().setVisible(False)
        self.sim_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.sim_table.cellChanged.connect(lambda *_: self._on_any_changed())
        return self.sim_table

    def _make_download_table(self) -> QTableWidget:
        self.dl_table = QTableWidget(0, 2)
        self.dl_table.setHorizontalHeaderLabels(["Text", "Href"])
        self.dl_table.verticalHeader().setVisible(False)
        self.dl_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.dl_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.dl_table.cellChanged.connect(lambda *_: self._on_any_changed())
        return self.dl_table

    def _make_resources_table(self) -> QTableWidget:
        self.res_table = QTableWidget(0, 1)
        self.res_table.setHorizontalHeaderLabels(["Video URL"])
        self.res_table.verticalHeader().setVisible(False)
        self.res_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.res_table.cellChanged.connect(lambda *_: self._on_any_changed())
        return self.res_table

    def _wrap_table_with_buttons(self, tbl: QTableWidget, noun: str) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0,0,0,0)
        v.addWidget(tbl, 1)
        row = QHBoxLayout()
        b_add = QPushButton(f"Add {noun}"); b_del = QPushButton("Remove Selected")
        b_add.clicked.connect(lambda: (tbl.insertRow(tbl.rowCount()), self._on_any_changed()))
        b_del.clicked.connect(lambda: (tbl.removeRow(tbl.currentRow()) if tbl.currentRow() >= 0 else None, self._on_any_changed()))
        row.addWidget(b_add); row.addWidget(b_del); row.addStretch(1); v.addLayout(row)
        return w

    # ---------- Components visibility ----------
    def _set_all_components(self, state: bool):
        self.chk_desc.setChecked(state); self.chk_videos.setChecked(state)
        self.chk_downloads.setChecked(state); self.chk_resources.setChecked(state)

    def _on_components_changed(self, _checked: bool):
        self._apply_component_visibility_to_editor(); self._on_any_changed()

    def _apply_component_visibility_to_editor(self):
        # Enable/disable section editor tabs for clarity
        cfg = {
            self.w_desc: self.chk_desc.isChecked(),
            self.w_videos: self.chk_videos.isChecked(),
            self.w_downloads: self.chk_downloads.isChecked(),
            self.w_resources: self.chk_resources.isChecked()
        }
        for w, on in cfg.items():
            idx = self.sections_tabs.indexOf(w)
            if hasattr(self.sections_tabs, "setTabVisible"):
                self.sections_tabs.setTabVisible(idx, on)
            else:
                self.sections_tabs.setTabEnabled(idx, on)

    # ---------- Context menu for collection table ----------
    def _collection_context_menu(self, pos):
        menu = QMenu(self)
        act_above = menu.addAction("Add Row Above")
        act_below = menu.addAction("Add Row Below")
        action = menu.exec_(QCursor.pos())
        r = self.collection_tbl.currentRow()
        if action == act_above:
            if r < 0: r = 0
            self.collection_tbl.insertRow(r); self._on_any_changed()
        elif action == act_below:
            r = 0 if r < 0 else r+1
            self.collection_tbl.insertRow(r); self._on_any_changed()

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
                self.current_path = None; self.path_label.setText(f"Folder: {path}")
                self._set_stats(None); self._clear_ui(); self._switch_page_mode("detail"); self._set_dirty(False); return
            if not (path.suffix.lower() in (".html",".htm")):
                self.current_path = None; self._clear_ui(); self._set_stats(None); self._switch_page_mode("detail"); self._set_dirty(False); return

            self.current_path = path; self.path_label.setText(f"File: {path}")
            text = ascii_sanitize(path.read_text(encoding="utf-8"))
            self._clear_ui()
            self.review_raw.setPlainText(text); self._review_dirty = False

            if BS4_AVAILABLE:
                soup = BeautifulSoup(text, "html.parser")
                is_detail = bool(soup.find("div", class_="tab-container"))
                if is_detail:
                    self._switch_page_mode("detail"); self._load_detail_from_soup(soup)
                else:
                    self._switch_page_mode("collection"); self._load_collection_page_from_soup(soup)
                self._load_nav_from_soup(soup)
            else:
                self._switch_page_mode("detail")
            self._set_stats(path); self._update_preview('schematic'); self._update_preview('layout'); self._set_dirty(False)
        finally:
            self._loading = False

    # ---------- Page mode ----------
    def _switch_page_mode(self, mode: str):
        self.page_mode = "collection" if str(mode).lower().startswith("coll") else "detail"
        idx_sections = self.tabs.indexOf(self.sections_host)
        idx_collection = self.tabs.indexOf(self.collection_host)
        if hasattr(self.tabs, "setTabVisible"):
            self.tabs.setTabVisible(idx_sections, self.page_mode == "detail")
            self.tabs.setTabVisible(idx_collection, self.page_mode == "collection")
        else:
            self.tabs.setTabEnabled(idx_sections, self.page_mode == "detail")
            self.tabs.setTabEnabled(idx_collection, self.page_mode == "collection")

    # ---------- Loaders ----------
    def _clear_ui(self):
        self.ed_title.clear(); self.ed_keywords.clear(); self.ed_description.clear(); self.ed_h1.clear(); self.ed_slogan.clear()
        for ed in (getattr(self, 'det_part', None), getattr(self, 'det_title', None), getattr(self, 'det_board', None),
                   getattr(self, 'det_pieces', None), getattr(self, 'det_panel', None),
                   getattr(self, 'sch_src', None), getattr(self, 'sch_alt', None),
                   getattr(self, 'lay_src', None), getattr(self, 'lay_alt', None)):
            if isinstance(ed, QLineEdit): ed.clear()
        for tbl in (getattr(self, 'sim_table', None), getattr(self, 'dl_table', None), getattr(self, 'res_table', None), getattr(self, 'nav_tbl', None)):
            if isinstance(tbl, QTableWidget):
                tbl.blockSignals(True); tbl.setRowCount(0); tbl.blockSignals(False)
        if hasattr(self, "sch_preview"): self.sch_preview.set_pixmap(None)
        if hasattr(self, "lay_preview"): self.lay_preview.set_pixmap(None)
        if hasattr(self, "desc_seed"): self.desc_seed.blockSignals(True); self.desc_seed.clear(); self.desc_seed.blockSignals(False)
        if hasattr(self, "desc_generated"): self.desc_generated.clear()
        self.review_raw.blockSignals(True); self.review_raw.clear(); self.review_raw.blockSignals(False)
        self._review_dirty = False
        self._set_ai_status_idle()
        # reset components to default show
        for c in (getattr(self,'chk_desc',None), getattr(self,'chk_videos',None), getattr(self,'chk_downloads',None), getattr(self,'chk_resources',None)):
            if isinstance(c, QCheckBox): c.blockSignals(True); c.setChecked(True); c.blockSignals(False)
        self._apply_component_visibility_to_editor()

    def _load_detail_from_soup(self, soup: BeautifulSoup):
        title = (soup.title.string if soup.title and soup.title.string else "") if soup.title else ""
        self.ed_title.setText((title or "").strip())
        kw = soup.find("meta", attrs={"name":"keywords"}); self.ed_keywords.setPlainText(kw["content"].strip() if kw and kw.has_attr("content") else "")
        desc = soup.find("meta", attrs={"name":"description"}); self.ed_description.setPlainText(desc["content"].strip() if desc and desc.has_attr("content") else "")
        h1 = soup.find("h1"); self.ed_h1.setText(h1.get_text(strip=True) if h1 else "")
        slog = soup.find("p", class_="slogan"); self.ed_slogan.setText(slog.get_text(strip=True) if slog else "")

        details = soup.find("div", class_="tab-content", id="details")
        def _get_detail(label: str) -> str:
            if not details: return ""
            for p in details.find_all("p"):
                strong = p.find("strong")
                if not strong: continue
                if strong.get_text(strip=True).rstrip(":").lower() != label.lower(): continue
                full = p.get_text(" ", strip=True)
                return re.sub(rf"^{re.escape(strong.get_text(strip=True).rstrip(':'))}\s*:?\s*", "", full, flags=re.I)
            return ""
        self.det_part.setText(_get_detail("Part No"))
        self.det_title.setText(_get_detail("Title"))
        self.det_board.setText(_get_detail("Board Size"))
        self.det_pieces.setText(_get_detail("Pieces per Panel"))
        self.det_panel.setText(_get_detail("Panel Size"))

        # Component flags from tab buttons
        f_desc, f_vids, f_dl, f_res = self._read_component_flags(soup)
        for chk, val in ((self.chk_desc,f_desc),(self.chk_videos,f_vids),(self.chk_downloads,f_dl),(self.chk_resources,f_res)):
            chk.blockSignals(True); chk.setChecked(val); chk.blockSignals(False)
        self._apply_component_visibility_to_editor()

        # Description
        desc_div = soup.find("div", class_="tab-content", id="description")
        seed_text = ""; gen_html = ""
        if desc_div:
            h3s = desc_div.find(["h3","h4"], string=re.compile(r"^\s*AI\s*Seed\s*$", re.I))
            if h3s:
                n = h3s.find_next_sibling()
                while n and not getattr(n, "name", None): n = n.next_sibling
                if n and getattr(n, "name", "") in ("p","div"): seed_text = n.get_text("\n", strip=True)
            h3g = desc_div.find(["h3","h4"], string=re.compile(r"^\s*AI\s*Generated\s*$", re.I))
            gen_div = None
            if h3g: gen_div = h3g.find_next_sibling("div", class_="generated")
            if gen_div: gen_html = gen_div.decode_contents()
        self.desc_seed.blockSignals(True); self.desc_seed.setPlainText(seed_text or ""); self.desc_seed.blockSignals(False)
        self.desc_generated.setHtml(gen_html or "")

        # Videos
        self._populate_iframe_table(self.sim_table, soup.find("div", class_="tab-content", id="simulation"))

        # Schematic / Layout
        sch = soup.find("div", class_="tab-content", id="schematic")
        img = (sch.find("img", class_="zoomable") if sch else None) or (sch.find("img") if sch else None)
        self.sch_src.setText(img.get("src","") if img else ""); self.sch_alt.setText(img.get("alt","") if img else "")
        lay = soup.find("div", class_="tab-content", id="layout")
        limg = (lay.find("img", class_="zoomable") if lay else None) or (lay.find("img") if lay else None)
        self.lay_src.setText(limg.get("src","") if limg else ""); self.lay_alt.setText(limg.get("alt","") if limg else "")

        # Downloads
        dl = soup.find("div", class_="tab-content", id="downloads")
        self.dl_table.blockSignals(True); self.dl_table.setRowCount(0)
        if dl:
            for a in dl.find_all("a"):
                r = self.dl_table.rowCount(); self.dl_table.insertRow(r)
                self.dl_table.setItem(r, 0, QTableWidgetItem(a.get_text(strip=True)))
                self.dl_table.setItem(r, 1, QTableWidgetItem(a.get("href","")))
        self.dl_table.blockSignals(False)

        # Resources
        self._populate_iframe_table(self.res_table, soup.find("div", class_="tab-content", id="resources"))

    def _read_component_flags(self, soup: BeautifulSoup):
        # Default True if buttons present; else False (if missing)
        present = set()
        tabs = soup.find("div", class_="tabs")
        if tabs:
            for b in tabs.find_all("button", class_="tab"):
                oc = b.get("onclick","")
                m = re.search(r"showTab\('([^']+)'", oc)
                if m: present.add(m.group(1))
        # If tabs not found, infer from sections (be conservative: True if section exists)
        def exists(sec_id): return soup.find("div", id=sec_id, class_="tab-content") is not None
        f_desc = "description" in present if tabs else exists("description")
        f_vids = "simulation" in present if tabs else exists("simulation")
        f_dl   = "downloads" in present if tabs else exists("downloads")
        f_res  = "resources" in present if tabs else exists("resources")
        return f_desc, f_vids, f_dl, f_res

    def _load_collection_page_from_soup(self, soup: BeautifulSoup):
        title = (soup.title.string if soup.title and soup.title.string else "") if soup.title else ""
        self.ed_title.setText((title or "").strip())
        kw = soup.find("meta", attrs={"name":"keywords"})
        self.ed_keywords.setPlainText(kw["content"].strip() if kw and kw.has_attr("content") else "")
        desc = soup.find("meta", attrs={"name":"description"})
        self.ed_description.setPlainText(desc["content"].strip() if desc and desc.has_attr("content") else "")
        h1 = soup.find("h1"); self.ed_h1.setText(h1.get_text(strip=True) if h1 else "")
        slog = soup.find("p", class_="slogan"); self.ed_slogan.setText(slog.get_text(strip=True) if slog else "")

        self.collection_tbl.blockSignals(True); self.collection_tbl.setRowCount(0)
        tbl = None; main = soup.find("main")
        if main: tbl = main.find("table")
        if not tbl: tbl = soup.find("table")
        if tbl:
            tbody = tbl.find("tbody") or tbl
            for tr in tbody.find_all("tr"):
                tds = tr.find_all(["td","th"])
                if not tds:
                    continue
                part = tds[0].get_text(strip=True) if len(tds) >= 1 else ""
                title_text, href = "", ""
                if len(tds) >= 2:
                    a = tds[1].find("a")
                    if a:
                        title_text = a.get_text(strip=True); href = a.get("href","")
                    else:
                        title_text = tds[1].get_text(strip=True)
                pieces = tds[2].get_text(strip=True) if len(tds) >= 3 else ""
                r = self.collection_tbl.rowCount(); self.collection_tbl.insertRow(r)
                self.collection_tbl.setItem(r, 0, QTableWidgetItem(part))
                self.collection_tbl.setItem(r, 1, QTableWidgetItem(title_text))
                self.collection_tbl.setItem(r, 2, QTableWidgetItem(href))
                self.collection_tbl.setItem(r, 3, QTableWidgetItem(pieces))
        self.collection_tbl.blockSignals(False)

    def _load_nav_from_soup(self, soup: BeautifulSoup):
        self.nav_tbl.blockSignals(True); self.nav_tbl.setRowCount(0)
        nav = soup.find("nav")
        if nav:
            for a in nav.find_all("a"):
                r = self.nav_tbl.rowCount(); self.nav_tbl.insertRow(r)
                self.nav_tbl.setItem(r, 0, QTableWidgetItem(a.get_text(strip=True)))
                self.nav_tbl.setItem(r, 1, QTableWidgetItem(a.get("href","")))
        self.nav_tbl.blockSignals(False)

    # ---------- Helpers ----------
    def _populate_iframe_table(self, table: QTableWidget, container):
        table.blockSignals(True); table.setRowCount(0)
        if container:
            for ifr in container.find_all("iframe"):
                src = ifr.get("src","").strip()
                r = table.rowCount(); table.insertRow(r); table.setItem(r, 0, QTableWidgetItem(src))
        table.blockSignals(False)

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

    def _move_row(self, tbl: QTableWidget, delta: int):
        r = tbl.currentRow()
        if r < 0: return
        nr = max(0, min(r + delta, tbl.rowCount()-1))
        if nr == r: return
        tbl.insertRow(nr)
        for c in range(tbl.columnCount()):
            it = tbl.takeItem(r + (1 if nr<r else 0), c)
            if it is None: it = QTableWidgetItem("")
            tbl.setItem(nr, c, it)
        tbl.removeRow(r + (1 if nr<r else 0))
        tbl.setCurrentCell(nr, 0); self._on_any_changed()

    # ---------- Image previews ----------
    def _resolve_img_path(self, src: str) -> Optional[Path]:
        if not src or not self.current_path: return None
        u = urlparse(src)
        if u.scheme in ("http","https","data"): return None
        raw = unquote(u.path); p = Path(raw)
        if p.is_absolute(): return p if p.exists() else None
        candidate = (self.current_path.parent / p).resolve()
        return candidate if candidate.exists() else None

    def _update_preview(self, kind: str):
        if kind == 'schematic':
            src = self.sch_src.text().strip(); lbl = self.sch_preview
        else:
            src = self.lay_src.text().strip(); lbl = self.lay_preview
        path = self._resolve_img_path(src)
        if path and path.exists():
            pm = QPixmap(str(path)); lbl.set_pixmap(pm if not pm.isNull() else None)
        else:
            lbl.set_pixmap(None)

    # ---------- PN → image path ----------
    def _update_image_field_from_pn(self, field: QLineEdit, pn: str, kind: str):
        import os
        cur = (field.text() or "").strip()
        dirpath = "../images"; ext = "png"; nn = "01" if kind == "schematic" else None
        if cur:
            d = os.path.dirname(cur) or dirpath; dirpath = d
            m = re.search(r"\.([A-Za-z0-9]+)$", cur)
            if m: ext = m.group(1)
            if kind == "schematic":
                m2 = re.search(r"_schematic_(\d+)\.[A-Za-z0-9]+$", cur)
                if m2: nn = m2.group(1)
        filename = f"{pn}_schematic_{nn}.{ext}" if kind=="schematic" else f"{pn}_components_top.{ext}"
        new_path = (dirpath.rstrip("/").rstrip("\\") + "/" + filename)
        field.blockSignals(True); field.setText(new_path); field.blockSignals(False)
        self._update_preview('schematic' if kind=='schematic' else 'layout')

    def _on_part_changed(self, _text=None):
        pn = (self.det_part.text() or "").strip()
        if not pn: return
        self._update_image_field_from_pn(self.sch_src, pn, kind="schematic")
        self._update_image_field_from_pn(self.lay_src, pn, kind="layout")
        self._on_any_changed()

    # ---------- Save / Update ----------
    def save_from_form(self, silent: bool=False):
        if not self.current_path or not self.current_path.exists():
            if not silent: self._info("Save", "Select an HTML file first.")
            return
        if not BS4_AVAILABLE:
            if not silent: self._warn("BeautifulSoup required", "pip install beautifulsoup4")
            return
        soup = self._build_soup_from_ui(use_template=False)
        out_txt = minipcb_format_html(soup)
        try:
            tmp = self.current_path.with_suffix(self.current_path.suffix + f".tmp.{os.getpid()}.{now_stamp()}")
            tmp.write_text(out_txt, encoding="utf-8"); os.replace(str(tmp), str(self.current_path))
        except Exception as e:
            try:
                if 'tmp' in locals() and tmp.exists(): tmp.unlink()
            except Exception: pass
            if not silent: self._error("Save error", f"Failed to save:\n{e}")
            return
        self._set_stats(self.current_path); self._set_dirty(False)

    def update_html_to_template(self):
        if not self.current_path or not self.current_path.exists():
            self._info("Update", "Select a file to update."); return
        if not BS4_AVAILABLE:
            self._warn("BeautifulSoup required", "pip install beautifulsoup4"); return
        soup = self._build_soup_from_ui(use_template=True)
        out_txt = minipcb_format_html(soup)
        try:
            tmp = self.current_path.with_suffix(self.current_path.suffix + f".upd.{os.getpid()}.{now_stamp()}")
            tmp.write_text(out_txt, encoding="utf-8"); os.replace(str(tmp), str(self.current_path))
        except Exception as e:
            try:
                if 'tmp' in locals() and tmp.exists(): tmp.unlink()
            except Exception: pass
            self._error("Update error", f"Failed to update:\n{e}"); return
        self._set_stats(self.current_path); self._set_dirty(False)

    # ---------- Build soup from current UI ----------
    def _build_soup_from_ui(self, use_template: bool) -> BeautifulSoup:
        if use_template:
            html = self._template_html(self.page_mode); soup = BeautifulSoup(html, "html.parser")
        else:
            txt = self.current_path.read_text(encoding="utf-8"); soup = BeautifulSoup(txt, "html.parser")
            if (self.page_mode == "detail" and not soup.find("div", class_="tab-container")) or \
               (self.page_mode == "collection" and soup.find("div", class_="tab-container")):
                soup = BeautifulSoup(self._template_html(self.page_mode), "html.parser")

        self._upsert_metadata_into_soup(soup)
        self._upsert_nav_into_soup(soup)

        if self.page_mode == "collection":
            self._save_collection_into_soup(soup); self._strip_detail_scripts(soup)
        else:
            self._save_detail_into_soup(soup); self._ensure_detail_scripts(soup)
        return soup

    def _strip_detail_scripts(self, soup: BeautifulSoup):
        lb = soup.find(id="lightbox"); 
        if lb: lb.decompose()
        for s in soup.find_all("script"): s.decompose()

    def _ensure_detail_scripts(self, soup: BeautifulSoup):
        if not soup.head: soup.html.insert(0, soup.new_tag("head"))
        head = soup.head
        if not head.find(string=re.compile(r"Google tag", re.I)):
            head.append(soup.new_string("\n")); head.append(soup.new_string("<!-- Google tag (gtag.js) -->")); head.append(soup.new_string("\n"))
            s1 = soup.new_tag("script"); s1["async"] = True; s1["src"] = "https://www.googletagmanager.com/gtag/js?id=G-9ZM2D6XGT2"; head.append(s1)
            s2 = soup.new_tag("script"); s2.string = (
                "window.dataLayer = window.dataLayer || [];\n"
                "function gtag(){dataLayer.push(arguments);} \n"
                "gtag('js', new Date()); \n"
                "gtag('config', 'G-9ZM2D6XGT2');"
            ); head.append(s2)

        body = soup.body or soup
        if not body.find(id="lightbox"):
            lb = soup.new_tag("div", id="lightbox", **{"aria-hidden":"true","role":"dialog","aria-label":"Image viewer"})
            img = soup.new_tag("img", id="lightbox-img", alt="Expanded image"); lb.append(img); body.append(lb)
        has_tab_js = any(s.string and "showTab(" in s.string for s in body.find_all("script"))
        if not has_tab_js:
            js = (
              "function showTab(id, btn) {\n"
              "  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));\n"
              "  document.querySelectorAll('.tabs .tab').forEach(el => el.classList.remove('active'));\n"
              "  var pane = document.getElementById(id);\n"
              "  if (pane) pane.classList.add('active');\n"
              "  if (btn) btn.classList.add('active');\n"
              "}\n\n"
              "const lb = document.getElementById('lightbox');\n"
              "const lbImg = document.getElementById('lightbox-img');\n"
              "function openLightbox(imgEl) {\n"
              "  const src = (imgEl.dataset && imgEl.dataset.full) ? imgEl.dataset.full : imgEl.src;\n"
              "  lbImg.src = src; lb.classList.add('open'); lb.setAttribute('aria-hidden','false'); document.body.classList.add('no-scroll');\n"
              "}\n"
              "function closeLightbox() {\n"
              "  lb.classList.remove('open'); lb.setAttribute('aria-hidden','true'); document.body.classList.remove('no-scroll'); setTimeout(() => { lbImg.src=''; }, 150);\n"
              "}\n"
              "lb && lb.addEventListener('click', (e) => { if (e.target === lb) closeLightbox(); });\n"
              "window.addEventListener('keydown', (e) => {\n"
              "  if (e.key === 'Escape' && lb && lb.classList.contains('open')) closeLightbox();\n"
              "});\n"
            )
            s = soup.new_tag("script"); s.string = js; body.append(s)

    # ---------- Common upserts ----------
    def _upsert_metadata_into_soup(self, soup: BeautifulSoup):
        def ensure_head():
            if not soup.head:
                if not soup.html: soup.append(soup.new_tag("html"))
                soup.html.insert(0, soup.new_tag("head"))
            return soup.head
        head = ensure_head()
        new_title = self.ed_title.text().strip()
        if soup.title:
            if soup.title.string: soup.title.string.replace_with(new_title)
            else: soup.title.string = new_title
        else:
            t = soup.new_tag("title"); t.string = new_title; head.append(t)
        def upsert_meta(name: str, value: str):
            tag = head.find("meta", attrs={"name": name})
            if tag is None:
                tag = soup.new_tag("meta"); tag.attrs["name"] = name; head.append(tag)
            tag.attrs["content"] = value
        upsert_meta("keywords", condense_meta(self.ed_keywords.toPlainText()))
        upsert_meta("description", condense_meta(self.ed_description.toPlainText()))
        new_h1 = self.ed_h1.text().strip()
        h1 = soup.find("h1")
        if h1: h1.clear(); h1.append(new_h1)
        else:
            parent = soup.find("header") or soup.body or soup.html
            if parent:
                nh = soup.new_tag("h1"); nh.string = new_h1
                if parent.contents: parent.insert(0, nh)
                else: parent.append(nh)
        new_slogan = self.ed_slogan.text().strip()
        slog = soup.find("p", class_="slogan")
        if slog: slog.clear(); slog.append(new_slogan)
        else:
            parent = soup.find("header") or soup.body or soup.html
            if parent:
                ps = soup.new_tag("p", **{"class":"slogan"}); ps.string = new_slogan; parent.append(ps)

    def _upsert_nav_into_soup(self, soup: BeautifulSoup):
        nav = soup.find("nav")
        if not nav:
            nav = soup.new_tag("nav"); cont = soup.new_tag("div", **{"class":"nav-container"})
            ul = soup.new_tag("ul", **{"class":"nav-links"}); cont.append(ul); nav.append(cont)
            body = soup.body or soup; body.insert(0, nav)
        ul = nav.find("ul", class_="nav-links")
        if not ul:
            ul = soup.new_tag("ul", **{"class":"nav-links"}); nav.append(ul)
        for ch in list(ul.children):
            if isinstance(ch, Tag): ch.decompose()
        for r in range(self.nav_tbl.rowCount()):
            text = self.nav_tbl.item(r,0).text().strip() if self.nav_tbl.item(r,0) else ""
            href = self.nav_tbl.item(r,1).text().strip() if self.nav_tbl.item(r,1) else ""
            if not (text or href): continue
            li = soup.new_tag("li"); a = soup.new_tag("a", href=href or "#"); a.string = text or href
            li.append(a); ul.append(li)

    # ---------- Detail save ----------
    def _ensure_container_and_tabs_div(self, soup: BeautifulSoup):
        main = soup.find("main")
        if not main:
            main = soup.new_tag("main"); (soup.body or soup).append(main)
        tabc = soup.find("div", class_="tab-container")
        if not tabc:
            tabc = soup.new_tag("div", **{"class":"tab-container"}); main.append(tabc)
        tabs = tabc.find("div", class_="tabs")
        if not tabs:
            tabs = soup.new_tag("div", **{"class":"tabs"}); tabc.insert(0, tabs)
        return tabc, tabs

    def _ensure_section(self, soup: BeautifulSoup, sec_id: str, heading_text: str):
        tabc, _ = self._ensure_container_and_tabs_div(soup)
        div = tabc.find("div", class_="tab-content", id=sec_id)
        if not div:
            div = soup.new_tag("div", **{"class":"tab-content", "id":sec_id})
            tabc.append(div)
        h2 = div.find("h2")
        if not h2:
            h2 = soup.new_tag("h2"); h2.string = heading_text; div.insert(0, h2)
        else:
            h2.string = heading_text
        return div

    def _mark_section_hidden(self, soup: BeautifulSoup, sec_id: str, hidden: bool):
        div = soup.find("div", class_="tab-content", id=sec_id)
        if not div: return
        if hidden: div["data-hidden"] = "true"
        else: div.attrs.pop("data-hidden", None)

    def _rebuild_tabs_header(self, soup: BeautifulSoup):
        tabc, tabs = self._ensure_container_and_tabs_div(soup)
        # Build enabled mapping/order
        enabled = {
            "details": True,
            "description": self.chk_desc.isChecked(),
            "simulation": self.chk_videos.isChecked(),
            "schematic": True,
            "layout": True,
            "downloads": self.chk_downloads.isChecked(),
            "resources": self.chk_resources.isChecked(),
        }
        order = [("details","Details"), ("description","Description"), ("simulation","Videos"),
                 ("schematic","Schematic"), ("layout","Layout"), ("downloads","Downloads"), ("resources","Additional Resources")]
        # Determine active content
        active_div = tabc.find("div", class_="tab-content", id=re.compile(r".*"), attrs={"class":re.compile(r"\bactive\b")})
        active_id = active_div.get("id") if active_div else "schematic"
        if active_id not in enabled or not enabled.get(active_id, False):
            active_id = "schematic"
        # Rebuild buttons
        for ch in list(tabs.children):
            if isinstance(ch, Tag): ch.decompose()
        for sec_id, label in order:
            if not enabled.get(sec_id, False): continue
            btn = soup.new_tag("button", **{"class":"tab" + (" active" if sec_id==active_id else ""), "onclick":f"showTab('{sec_id}', this)"})
            btn.string = label; tabs.append(btn)
        # Ensure only one active
        for div in tabc.find_all("div", class_="tab-content"):
            classes = (div.get("class") or [])
            if "tab-content" not in classes: continue
            if div.get("id") == active_id:
                if "active" not in classes: classes.append("active")
            else:
                classes = [c for c in classes if c != "active"]
            div["class"] = classes

    def _save_detail_into_soup(self, soup: BeautifulSoup):
        # ----- Details -----
        det_div = self._ensure_section(soup, "details", "PCB Details")
        for node in list(det_div.find_all(recursive=False))[1:]: node.decompose()
        def mk_detail(label: str, value: str):
            p = soup.new_tag("p"); strong = soup.new_tag("strong"); strong.string = f"{label}:"
            p.append(strong); p.append(" " + value); return p
        det_div.append(mk_detail("Part No", self.det_part.text().strip()))
        det_div.append(mk_detail("Title", self.det_title.text().strip()))
        det_div.append(mk_detail("Board Size", self.det_board.text().strip()))
        det_div.append(mk_detail("Pieces per Panel", self.det_pieces.text().strip()))
        det_div.append(mk_detail("Panel Size", self.det_panel.text().strip()))

        # ----- Description -----
        dsc_div = self._ensure_section(soup, "description", "Description")
        for node in list(dsc_div.find_all(recursive=False))[1:]: node.decompose()
        h3s = soup.new_tag("h3"); h3s.string = "AI Seed"; dsc_div.append(h3s)
        pseed = soup.new_tag("p"); pseed.string = self.desc_seed.toPlainText().strip(); dsc_div.append(pseed)
        h3g = soup.new_tag("h3"); h3g.string = "AI Generated"; dsc_div.append(h3g)
        wrap = soup.new_tag("div", **{"class":"generated"})
        frag = self.desc_generated.toHtml(); clean_nodes = self._sanitize_ai_fragment(frag, soup)
        for node in clean_nodes: wrap.append(node)
        dsc_div.append(wrap)

        # ----- Videos (id=simulation) -----
        sim_div = self._ensure_section(soup, "simulation", "Videos")
        for node in list(sim_div.find_all(recursive=False))[1:]: node.decompose()
        self._write_iframe_list(soup, sim_div, self._table_to_list(self.sim_table))

        # ----- Schematic -----
        sch_div = self._ensure_section(soup, "schematic", "Schematic")
        for node in list(sch_div.find_all(recursive=False))[1:]: node.decompose()
        lb = soup.new_tag("div", **{"class":"lightbox-container"})
        img = soup.new_tag("img", **{
            "class":"zoomable", "src": self.sch_src.text().strip(),
            "alt": self.sch_alt.text().strip() or "Schematic",
        })
        img.attrs["onclick"] = "openLightbox(this)"
        lb.append(img); sch_div.append(lb)

        # ----- Layout -----
        lay_div = self._ensure_section(soup, "layout", "Layout")
        for node in list(lay_div.find_all(recursive=False))[1:]: node.decompose()
        lb2 = soup.new_tag("div", **{"class":"lightbox-container"})
        limg = soup.new_tag("img", **{
            "class":"zoomable", "src": self.lay_src.text().strip(),
            "alt": self.lay_alt.text().strip() or "Top view of miniPCB",
        })
        limg.attrs["onclick"] = "openLightbox(this)"
        lb2.append(limg); lay_div.append(lb2)

        # ----- Downloads -----
        dl_div = self._ensure_section(soup, "downloads", "Downloads")
        for node in list(dl_div.find_all(recursive=False))[1:]: node.decompose()
        ul = soup.new_tag("ul", **{"class":"download-list"})
        for text, href in self._iter_download_rows():
            if not (text or href): continue
            li = soup.new_tag("li"); a = soup.new_tag("a", href=href or "#", target="_blank", rel="noopener"); a.string = text or href or "Download"
            li.append(a); ul.append(li)
        dl_div.append(ul)

        # ----- Resources -----
        res_div = self._ensure_section(soup, "resources", "Additional Resources")
        for node in list(res_div.find_all(recursive=False))[1:]: node.decompose()
        self._write_iframe_list(soup, res_div, self._table_to_list(self.res_table))

        # Mark hidden sections based on checkboxes (data not lost)
        self._mark_section_hidden(soup, "description", not self.chk_desc.isChecked())
        self._mark_section_hidden(soup, "simulation", not self.chk_videos.isChecked())
        self._mark_section_hidden(soup, "downloads", not self.chk_downloads.isChecked())
        self._mark_section_hidden(soup, "resources", not self.chk_resources.isChecked())

        # Rebuild the tab buttons to include only enabled components
        self._rebuild_tabs_header(soup)

    def _sanitize_ai_fragment(self, html_fragment: str, soup: BeautifulSoup) -> List[Tag]:
        try:
            frag = BeautifulSoup(html_fragment or "", "html.parser")
        except Exception:
            frag = BeautifulSoup("", "html.parser")
        body = frag.find("body") or frag
        result: List[Tag] = []
        for node in list(body.children):
            if isinstance(node, NavigableString):
                txt = _text_collapse(str(node))
                if txt:
                    p = soup.new_tag("p"); p.string = txt; result.append(p)
                continue
            if isinstance(node, Tag):
                cleaned = self._strip_styles_deep(node, soup); result.append(cleaned)
        return result

    def _strip_styles_deep(self, node: Tag, soup: BeautifulSoup) -> Tag:
        def clone(t: Tag) -> Tag:
            nt = soup.new_tag(t.name)
            keep = {"href","title","alt"}
            for k, v in (t.attrs or {}).items():
                if k in keep: nt.attrs[k] = v
            for c in t.children or []:
                if isinstance(c, NavigableString):
                    txt = _text_collapse(str(c))
                    if txt: nt.append(txt)
                elif isinstance(c, Tag):
                    nt.append(clone(c))
            return nt
        return clone(node)

    def _write_iframe_list(self, soup: BeautifulSoup, container, urls: List[str]):
        for url in urls:
            wrap = soup.new_tag("div", **{"class":"video-wrapper"})
            ifr = soup.new_tag("iframe", **{
                "width":"560", "height":"315", "src":url, "title":"YouTube video player", "frameborder":"0",
                "allow":"accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share",
                "allowfullscreen": True, "referrerpolicy":"strict-origin-when-cross-origin"
            })
            wrap.append(ifr); container.append(wrap)

    # ---------- Collection save ----------
    def _save_collection_into_soup(self, soup: BeautifulSoup):
        main = soup.find("main")
        if not main:
            main = soup.new_tag("main"); (soup.body or soup).append(main)
        section = main.find("section")
        if not section:
            section = soup.new_tag("section"); main.append(section)
        old_tbl = section.find("table") or main.find("table")
        if old_tbl: old_tbl.decompose()
        tbl = soup.new_tag("table")
        thead = soup.new_tag("thead"); trh = soup.new_tag("tr")
        for name in ("Part No", "Title", "Pieces per Panel"):
            th = soup.new_tag("th"); th.string = name; trh.append(th)
        thead.append(trh); tbl.append(thead)
        tbody = soup.new_tag("tbody")
        for r in range(self.collection_tbl.rowCount()):
            part = (self.collection_tbl.item(r,0).text().strip() if self.collection_tbl.item(r,0) else "")
            title_text = (self.collection_tbl.item(r,1).text().strip() if self.collection_tbl.item(r,1) else "")
            href = (self.collection_tbl.item(r,2).text().strip() if self.collection_tbl.item(r,2) else "")
            pieces = (self.collection_tbl.item(r,3).text().strip() if self.collection_tbl.item(r,3) else "")
            if not (part or title_text or href or pieces): continue
            tr = soup.new_tag("tr")
            td_part = soup.new_tag("td"); td_part.string = part; tr.append(td_part)
            td_title = soup.new_tag("td")
            if title_text or href:
                a = soup.new_tag("a", href=(href or "#")); a.string = title_text or href
                td_title.append(a)
            tr.append(td_title)
            td_pieces = soup.new_tag("td"); td_pieces.string = pieces; tr.append(td_pieces)
            tbody.append(tr)
        tbl.append(tbody); section.append(tbl)

    # ---------- Template ----------
    def _template_html(self, mode: str) -> str:
        year = datetime.date.today().year
        if mode == "collection":
            return f"""<!DOCTYPE html>
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
  <title></title>
  <link rel="stylesheet" href="/styles.css"/>
  <link rel="icon" type="image/png" href="/favicon.png"/>
  <meta name="keywords" content=""/>
  <meta name="description" content=""/>
</head>
<body>
  <nav><div class="nav-container"><ul class="nav-links"></ul></div></nav>
  <header><h1></h1><p class="slogan"></p></header>
  <main>
    <section>
      <table>
        <thead><tr><th>Part No</th><th>Title</th><th>Pieces per Panel</th></tr></thead>
        <tbody></tbody>
      </table>
    </section>
  </main>
  <footer>© {year} miniPCB. All rights reserved.</footer>
</body>
</html>"""
        else:
            return f"""<!DOCTYPE html>
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
  <title></title>
  <link rel="stylesheet" href="/styles.css"/>
  <link rel="icon" type="image/png" href="/favicon.png"/>
  <meta name="keywords" content=""/>
  <meta name="description" content=""/>
</head>
<body>
  <nav><div class="nav-container"><ul class="nav-links"></ul></div></nav>
  <header><h1></h1><p class="slogan"></p></header>
  <main>
    <div class="tab-container">
      <div class="tabs"></div> <!-- built during save -->
      <div id="details" class="tab-content"><h2>PCB Details</h2></div>
      <div id="description" class="tab-content"><h2>Description</h2><h3>AI Seed</h3><p></p><h3>AI Generated</h3><div class="generated"></div></div>
      <div id="simulation" class="tab-content"><h2>Videos</h2></div>
      <div id="schematic" class="tab-content active"><h2>Schematic</h2><div class="lightbox-container"><img class="zoomable" alt="Schematic" src="" onclick="openLightbox(this)"/></div></div>
      <div id="layout" class="tab-content"><h2>Layout</h2><div class="lightbox-container"><img class="zoomable" alt="Board Layout" src="" onclick="openLightbox(this)"/></div></div>
      <div id="downloads" class="tab-content"><h2>Downloads</h2><ul class="download-list"></ul></div>
      <div id="resources" class="tab-content"><h2>Additional Resources</h2></div>
    </div>
  </main>
  <footer>© {year} miniPCB. All rights reserved.</footer>
  <div id="lightbox" aria-hidden="true" role="dialog" aria-label="Image viewer"><img id="lightbox-img" alt="Expanded image"/></div>
  <script>
    function showTab(id, btn) {{
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tabs .tab').forEach(el => el.classList.remove('active'));
      var pane = document.getElementById(id);
      if (pane) pane.classList.add('active');
      if (btn) btn.classList.add('active');
    }}
    const lb = document.getElementById('lightbox');
    const lbImg = document.getElementById('lightbox-img');
    function openLightbox(imgEl) {{
      const src = (imgEl.dataset && imgEl.dataset.full) ? imgEl.dataset.full : imgEl.src;
      lbImg.src = src; lb.classList.add('open'); lb.setAttribute('aria-hidden','false'); document.body.classList.add('no-scroll');
    }}
    function closeLightbox() {{
      lb.classList.remove('open'); lb.setAttribute('aria-hidden','true'); document.body.classList.remove('no-scroll');
      setTimeout(() => {{ lbImg.src = ''; }}, 150);
    }}
    lb && lb.addEventListener('click', (e) => {{ if (e.target === lb) closeLightbox(); }});
    window.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape' && lb && lb.classList.contains('open')) closeLightbox();
    }});
  </script>
</body>
</html>"""

    # ---------- Review ----------
    def _on_tabs_changed(self, idx: int):
        try:
            if self.tabs.widget(idx) is self.review_tab and BS4_AVAILABLE and self.current_path and self.current_path.exists():
                soup = self._build_soup_from_ui(use_template=False)
                self.review_raw.blockSignals(True); self.review_raw.setPlainText(minipcb_format_html(soup))
                self.review_raw.blockSignals(False); self._review_dirty = False
        except Exception:
            pass

    def _on_review_changed(self):
        if self._loading: return
        self._review_dirty = True; self._set_dirty(True)

    # ---------- Settings + FS actions ----------
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
        mode = "detail"
        if self._ask_yes_no("Page type", "Is this a collection page?\n(Yes = Collection, No = Board/Detail)"):
            mode = "collection"
        html = self._template_html(mode)
        try:
            target.write_text(html, encoding="utf-8")
        except Exception as e:
            self._error("Error", f"Failed to create file:\n{e}"); return
        sidx = self.fs_model.index(str(target))
        if sidx.isValid():
            pidx = self.proxy.mapFromSource(sidx); 
            if pidx.isValid(): self.tree.setCurrentIndex(pidx)

    def rename_item(self):
        path = self.selected_path()
        if not path:
            self._info("Rename", "Select a file or folder to rename."); return
        new_name, ok = self._ask_text("Rename", "New name:", default=path.name)
        if not ok or not new_name.strip(): return
        new_path = path.parent / new_name.strip()
        if new_path.exists():
            self._warn("Exists", "Target name already exists."); return
        try:
            path.rename(new_path)
            if self.current_path and self.current_path == path:
                self.current_path = new_path; self.path_label.setText(f"File: {new_path}")
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
            self._info("Open Location", "Select a folder or file first."); return
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
            self.stat_lines.setText("-"); self.stat_words.setText("-"); self.stat_chars.setText("-"); self.stat_edited.setText("-"); return
        try:
            txt = path.read_text(encoding="utf-8", errors="ignore")
            lines = txt.count("\n") + (1 if txt and not txt.endswith("\n") else 0)
            words = len(re.findall(r"\S+", txt)); chars = len(txt)
            mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime).isoformat(sep=" ", timespec="seconds")
            self.stat_lines.setText(str(lines)); self.stat_words.setText(str(words)); self.stat_chars.setText(str(chars)); self.stat_edited.setText(mtime)
        except Exception:
            self.stat_lines.setText("?"); self.stat_words.setText("?"); self.stat_chars.setText("?"); self.stat_edited.setText("?")

    # ---------- Dirty / Autosave ----------
    def _on_any_changed(self):
        if self._loading: return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool):
        if dirty:
            self._dirty = True; self.autosave_secs_left = self.autosave_interval
            self.autosave_label.setText(f"Autosave in: {self.autosave_secs_left}s")
            self.path_label.setStyleSheet("color:#4CE06A; font-weight:600;")
        else:
            self._dirty = False; self.autosave_secs_left = self.autosave_interval
            self.autosave_label.setText("Autosave in: --s")
            self.path_label.setStyleSheet("")

    def _autosave_tick(self):
        if not self.current_path:
            self.autosave_label.setText("Autosave in: --s"); return
        if self._dirty:
            self.autosave_secs_left = max(0, self.autosave_secs_left - 1)
            self.autosave_label.setText(f"Autosave in: {self.autosave_secs_left}s")
            if self.autosave_secs_left == 0:
                self.save_from_form(silent=True)
        else:
            self.autosave_label.setText("Autosave in: --s")

    # ---------- AI ----------
    def _start_desc_ai(self):
        if self._ai_running: return
        if not OPENAI_AVAILABLE:
            self._warn("OpenAI not installed", "pip install openai"); return
        if not self.openai_key:
            self._set_api_key()
            if not self.openai_key:
                self._warn("API key required", "OpenAI API key not set."); return
        seed = self.desc_seed.toPlainText().strip(); page_title = self.ed_title.text().strip()
        h1 = self.ed_h1.text().strip(); part_no = self.det_part.text().strip()
        self._ai_eta_sec = 60; self._ai_start_ts = datetime.datetime.now()
        self._ai_running = True; self.btn_desc_generate.setEnabled(False)
        self._update_ai_label(elapsed=0, eta=self._ai_eta_sec, status="running"); self.ai_timer.start(250)
        self.worker = DescAIWorker(self.openai_key, self.openai_model, seed, page_title, h1, part_no, timeout=180)
        self.worker.finished.connect(self._on_desc_ai_finished); self.worker.start()

    def _set_ai_status_idle(self):
        self._ai_running = False; self._ai_start_ts = None; self._ai_eta_sec = None
        self.ai_timer.stop(); self.lbl_desc_ai.setText("AI: idle"); self.btn_desc_generate.setEnabled(True)

    def _tick_ai_ui(self):
        if not self._ai_running or not self._ai_start_ts: return
        elapsed = int((datetime.datetime.now() - self._ai_start_ts).total_seconds())
        self._update_ai_label(elapsed=elapsed, eta=self._ai_eta_sec, status="running")

    def _update_ai_label(self, elapsed: int, eta: Optional[int], status: str):
        def fmt(sec: Optional[int]) -> str:
            if sec is None: return "--:--"
            m, s = divmod(max(0, int(sec)), 60); return f"{m:02d}:{s:02d}"
        self.lbl_desc_ai.setText(f"AI: {fmt(elapsed)} / ETA ≈ {fmt(eta)}")

    def _on_desc_ai_finished(self, result: dict):
        elapsed = int(result.get("elapsed", 0))
        self._update_ai_label(elapsed=elapsed, eta=self._ai_eta_sec, status="done")
        self.ai_timer.stop(); self._ai_running = False; self.btn_desc_generate.setEnabled(True)
        ok = result.get("ok", False)
        if not ok:
            self._error("AI Error", result.get("error", "Unknown error")); return
        html = result.get("html","").strip()
        if html:
            clean_nodes = self._sanitize_ai_fragment(html, BeautifulSoup("<div></div>", "html.parser"))
            frag_html = "".join(str(n) for n in clean_nodes)
            self.desc_generated.setHtml(frag_html); self._on_any_changed()

    # ---------- Navigation picker ----------
    def _add_nav_link_via_picker(self):
        base = self.selected_path() or self.content_root
        cur_dir = base.parent if base.is_file() else base
        dlg = LinkPickerDialog(self, self.content_root, cur_dir)
        apply_windows_dark_titlebar(dlg)
        if dlg.exec_() == QDialog.Accepted:
            for rel in dlg.selected():
                text = Path(rel).stem.replace("_"," ").replace("-"," ").title()
                r = self.nav_tbl.rowCount(); self.nav_tbl.insertRow(r)
                self.nav_tbl.setItem(r, 0, QTableWidgetItem(text))
                href = "/" + rel if not rel.startswith("/") else rel
                self.nav_tbl.setItem(r, 1, QTableWidgetItem(href))
            self._on_any_changed()

# ---------- Boot ----------
def ensure_content_root() -> Path:
    settings = get_settings(); saved = settings.value(KEY_CONTENT_DIR, None)
    if saved and Path(saved).exists(): return Path(saved)
    root = default_content_root(); root.mkdir(parents=True, exist_ok=True); return root

def main():
    app = QApplication(sys.argv); app.setStyle(QStyleFactory.create("Fusion"))
    icon = make_emoji_icon("💠", px=220); app.setWindowIcon(icon)
    root = ensure_content_root()
    win = CatalogWindow(root, icon); win.show(); apply_windows_dark_titlebar(win)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
