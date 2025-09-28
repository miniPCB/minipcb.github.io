from pydoc import html
import re
import json
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit, QListWidget,
    QPushButton, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QPlainTextEdit, QComboBox, QDialog, QDialogButtonBox, QCheckBox, QGridLayout, QFileDialog,
    QMenu, QAction, QDialog, QDialogButtonBox, QFileDialog, QMenu, QAction, QSizePolicy, QLabel, QScrollArea,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSignalBlocker, QPointF, QDateTime
from PyQt5.QtGui import QPixmap, QTransform, QKeySequence

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None  # Fallbacks will be used

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    from PyQt5.QtCore import QUrl
except Exception:
    QWebEngineView = None
    QUrl = None

import os

# Optional BeautifulSoup; gracefully degrade if unavailable
try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None  # Fallbacks will be used

from services.template_loader import Templates
from services.html_service import HtmlService

class DownloadsDialog(QDialog):
    """
    Simple checkbox dialog for Downloads. Computes URLs from PN and REV.
    """
    def __init__(self, pn: str, rev: str, initial: dict[str, bool] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Downloads")
        self.pn = pn.strip()
        self.rev = rev.strip()

        self.chk_datasheet = QCheckBox("Datasheet (PDF)")
        self.chk_ltspice   = QCheckBox("LTspice File (.asc)")
        self.chk_gerbers   = QCheckBox("Gerber Files (.zip)")
        self.chk_cad       = QCheckBox("EAGLE 6.3 Files (.zip)")

        initial = initial or {}
        self.chk_datasheet.setChecked(initial.get("datasheet", True))
        self.chk_ltspice.setChecked(initial.get("ltspice", True))
        self.chk_gerbers.setChecked(initial.get("gerbers", False))
        self.chk_cad.setChecked(initial.get("cad", False))

        self.le_rev = QLineEdit(self.rev)
        self.le_rev.setPlaceholderText("e.g., A1-01")

        grid = QGridLayout(self)
        r = 0
        grid.addWidget(QLabel(f"PN: {self.pn or '(not set)'}"), r, 0, 1, 2); r += 1
        grid.addWidget(QLabel("Revision (for Gerbers/CAD):"), r, 0)
        grid.addWidget(self.le_rev, r, 1); r += 1
        grid.addWidget(self.chk_datasheet, r, 0, 1, 2); r += 1
        grid.addWidget(self.chk_ltspice,   r, 0, 1, 2); r += 1
        grid.addWidget(self.chk_gerbers,   r, 0, 1, 2); r += 1
        grid.addWidget(self.chk_cad,       r, 0, 1, 2); r += 1

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        grid.addWidget(btns, r, 0, 1, 2)

    def result_state(self) -> dict:
        rev = self.le_rev.text().strip()
        return {
            "datasheet": self.chk_datasheet.isChecked(),
            "ltspice":   self.chk_ltspice.isChecked(),
            "gerbers":   self.chk_gerbers.isChecked(),
            "cad":       self.chk_cad.isChecked(),
            "rev":       rev,
        }

class NavLinkDialog(QDialog):
    """
    Dialog to create/edit a navigation link.
    - Lets user enter Title and URL.
    - 'Browse…' chooses a file and the caller can convert to relative later if desired.
    """
    def __init__(self, title: str = "", href: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Navigation Link")
        self.setModal(True)

        self.le_title = QLineEdit(title)
        self.le_href = QLineEdit(href)
        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.clicked.connect(self._browse)

        form = QFormLayout()
        form.addRow("Title:", self.le_title)
        row = QHBoxLayout()
        row.addWidget(self.le_href)
        row.addWidget(self.btn_browse)
        form.addRow("URL:", row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)

    def _browse(self):
        # Let the user choose any HTML file
        fname, _ = QFileDialog.getOpenFileName(self, "Choose Page", "", "HTML files (*.html);;All files (*.*)")
        if fname:
            # leave raw path here; caller will convert to relative URL as needed
            self.le_href.setText(fname)

    def result(self) -> tuple[str, str]:
        return self.le_title.text().strip(), self.le_href.text().strip()

class SimpleUrlDialog(QDialog):
    def __init__(self, title: str, url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit URL")
        self.setModal(True)

        self.le_title = QLineEdit(title)
        self.le_url = QLineEdit(url)

        form = QFormLayout()
        form.addRow("Title (optional):", self.le_title)
        form.addRow("URL:", self.le_url)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)

    def result(self) -> tuple[str, str]:
        return self.le_title.text().strip(), self.le_url.text().strip()

class ReorderableList(QListWidget):
    """QListWidget that supports drag-to-reorder and emits once when the drop completes."""
    itemsReordered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)

    def dropEvent(self, event):
        super().dropEvent(event)     # perform the move
        self.itemsReordered.emit()   # one clean signal after reordering

class ScaledImageLabel(QLabel):
    """QLabel that scales an image to fit while keeping aspect ratio."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._orig_pixmap = None
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(240)

    def set_image_path(self, path: Path):
        pix = QPixmap(str(path))
        if pix.isNull():
            self._orig_pixmap = None
            self.setText(f"IMAGE NOT FOUND\n{path}")
            return
        self._orig_pixmap = pix
        self.setText("")
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        if not self._orig_pixmap:
            return
        w = max(1, self.width() - 8)
        h = max(1, self.height() - 8)
        scaled = self._orig_pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        super().setPixmap(scaled)

# ---- Drop-in: ZoomPanImageViewExactFit ----
from PyQt5.QtGui import QPixmap, QPainter, QTransform, QImageReader
from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QSizePolicy, QFrame
from PyQt5.QtCore import Qt, QTimer, QRectF

try:
    from PyQt5.QtWidgets import QOpenGLWidget
    _HAS_GL = True
except Exception:
    _HAS_GL = False

class ZoomPanImageView(QGraphicsView):
    """
    Exact-fit image view:
      • Auto-fits to use 100% of the available width/height (no cropping).
      • Turns scrollbars off while auto-fitting to avoid reserved gutter.
      • Wheel zoom under cursor, drag to pan, double-click toggles Fit <-> 100%.
      • Adaptive quality: Fast (crisp) when scale<1, Smooth when scale>=1.
      • No grainy downscale; fills all available space.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._item: QGraphicsPixmapItem | None = None
        self._img_size = None  # (w, h) in scene units
        self._auto_fit = True
        self._user_zoomed = False

        if _HAS_GL:
            try:
                self.setViewport(QOpenGLWidget())
            except Exception:
                pass

        # Quality options
        self.setRenderHints(QPainter.Antialiasing | QPainter.HighQualityAntialiasing)
        self.setCacheMode(QGraphicsView.CacheNone)  # avoid stale resamples
        self.setOptimizationFlags(QGraphicsView.DontAdjustForAntialiasing | QGraphicsView.DontSavePainterState)

        # Interaction & layout
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setFrameShape(QFrame.NoFrame)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(240)

        # Start with scrollbars hidden to prevent gutter during auto-fit
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    # ---------- Public API ----------
    def set_image_path(self, path):
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():
            self._scene.clear()
            self._item = None
            self._img_size = None
            self._scene.addText(f"IMAGE NOT FOUND\n{path}")
            self._auto_fit = True
            self._user_zoomed = False
            self._fit_exact_later()
            return
        self.set_pixmap(QPixmap.fromImage(img))

    def set_pixmap(self, pix: QPixmap):
        self._scene.clear()
        self._item = QGraphicsPixmapItem(pix)
        try:
            self._item.setTransformationMode(Qt.SmoothTransformation)
        except Exception:
            pass
        self._scene.addItem(self._item)
        rect = self._item.boundingRect()
        self._scene.setSceneRect(rect)
        self._img_size = (rect.width(), rect.height())

        self._auto_fit = True
        self._user_zoomed = False
        self.resetTransform()
        self._fit_exact_later()

    # ---------- Interaction ----------
    def wheelEvent(self, event):
        if not self._item:
            return super().wheelEvent(event)
        dy = event.angleDelta().y()
        if dy == 0:
            return
        factor = 1.15 if dy > 0 else 1/1.15
        self._zoom_step(factor)

    def mouseDoubleClickEvent(self, event):
        if not self._item:
            return super().mouseDoubleClickEvent(event)
        if self._auto_fit or not self._user_zoomed:
            self.actual_size()
        else:
            self.fit_to_window()
        event.accept()

    def keyPressEvent(self, event):
        k, m = event.key(), event.modifiers()
        if (m & Qt.ControlModifier) and k == Qt.Key_0:
            self.fit_to_window(); return
        if (m & Qt.ControlModifier) and k == Qt.Key_1:
            self.actual_size(); return
        if k in (Qt.Key_Plus, Qt.Key_Equal):
            self._zoom_step(1.15); return
        if k in (Qt.Key_Minus, Qt.Key_Underscore):
            self._zoom_step(1/1.15); return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_fit:
            self._fit_exact()

    # ---------- Commands ----------
    def fit_to_window(self):
        self._auto_fit = True
        self._user_zoomed = False
        self.resetTransform()
        self._fit_exact()

    def actual_size(self):
        self._auto_fit = False
        self._user_zoomed = True
        self.resetTransform()
        # Enable scrollbars in manual mode, if needed
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._apply_quality_for_scale()
        if self._item:
            self.centerOn(self._item)

    # ---------- Internals ----------
    def _zoom_step(self, factor: float):
        cur = self.transform().m11()
        new_scale = cur * factor
        if not (0.05 <= new_scale <= 50.0):
            return
        self.scale(factor, factor)
        self._auto_fit = False
        self._user_zoomed = True
        # Enable scrollbars when zooming by user
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._apply_quality_for_scale()

    def _fit_exact_later(self):
        self._fit_exact()
        QTimer.singleShot(0, self._fit_exact)

    def _fit_exact(self):
        if not self._item or not self._img_size:
            return
        # While auto-fitting, disable scrollbars so no gutter is reserved
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        vw = max(1, self.viewport().width())
        vh = max(1, self.viewport().height())
        iw, ih = self._img_size

        if iw <= 0 or ih <= 0:
            return

        # Exact uniform scale to fit, never crop
        sx = vw / iw
        sy = vh / ih
        scale = min(sx, sy)
        # small epsilon so we never trigger scrollbars due to rounding
        scale *= 0.999

        self.setTransform(QTransform.fromScale(scale, scale))
        self.centerOn(QRectF(0, 0, iw, ih).center())
        self._apply_quality_for_scale()

    def _apply_quality_for_scale(self):
        s = self.transform().m11()
        if not self._item:
            return
        if s < 1.0:
            # crisp downscale
            hints = self.renderHints() & ~QPainter.SmoothPixmapTransform
            self.setRenderHints(hints)
            try:
                self._item.setTransformationMode(Qt.FastTransformation)
            except Exception:
                pass
        else:
            hints = self.renderHints() | QPainter.SmoothPixmapTransform
            self.setRenderHints(hints)
            try:
                self._item.setTransformationMode(Qt.SmoothTransformation)
            except Exception:
                pass

class AiSeedsDialog(QDialog):
    """
    Editor for JSON stored in:
      <div id="ai-seeds"><script id="ai-seeds-json" type="application/json">{...}</script></div>

    Fields (flattened):
      - description_seed
      - testing_seed
      - fmea_seed

    Backward compatible: if only testing.dtp_seed / testing.atp_seed exist,
    they are concatenated into testing_seed on load.
    """
    def __init__(self, parent=None, seeds=None):
        super().__init__(parent)
        self.setWindowTitle("Edit AI Seeds")
        self.resize(720, 540)

        seeds = seeds or {}
        description_seed = seeds.get("description_seed", "")
        # prefer flattened key; else merge legacy dtp/atp if present
        testing_seed = seeds.get("testing_seed", "")
        if not testing_seed:
            t = seeds.get("testing", {}) if isinstance(seeds.get("testing"), dict) else {}
            parts = [(t.get("dtp_seed") or "").strip(), (t.get("atp_seed") or "").strip()]
            testing_seed = "\n".join([p for p in parts if p])

        fmea_seed = seeds.get("fmea_seed", "")

        self.txt_description = QPlainTextEdit(self)
        self.txt_description.setPlaceholderText("description_seed …")
        self.txt_description.setPlainText(description_seed)

        self.txt_testing = QPlainTextEdit(self)
        self.txt_testing.setPlaceholderText("testing_seed …")
        self.txt_testing.setPlainText(testing_seed)

        self.txt_fmea = QPlainTextEdit(self)
        self.txt_fmea.setPlaceholderText("fmea_seed …")
        self.txt_fmea.setPlainText(fmea_seed)

        form = QFormLayout(self)
        form.addRow("Description Seed:", self.txt_description)
        form.addRow("Testing Seed:", self.txt_testing)
        form.addRow("FMEA Seed:", self.txt_fmea)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def result_seeds(self):
        # Always return flattened shape
        return {
            "description_seed": self.txt_description.toPlainText().strip(),
            "testing_seed": self.txt_testing.toPlainText().strip(),
            "fmea_seed": self.txt_fmea.toPlainText().strip(),
        }


class MainTabs(QWidget):
    typeChanged = pyqtSignal(str)  # 'collection'|'board'|'other'

    def __init__(self, ctx, get_editor_text_callable=None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.get_editor_text = get_editor_text_callable

        # --- file/context state
        self.current_path: Path | None = None
        self.current_type: str = "other"
        self.templates = None
        self.htmlsvc: HtmlService | None = None
        self._suppress_form_signals = False

        # --- optional sections state/guards
        self._opt_checks: dict[str, QCheckBox] = {}
        self._opt_visibility: dict[str, bool] = {}
        self._is_updating_optionals: bool = False   # reentrancy guard for optionals
        self._current_html: str = ""                # last loaded/edited HTML

        # ---------- Outer layout ----------
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # ---------- View bar (optional sections checkboxes) ----------
        self._view_bar = QWidget(self)
        self._view_bar_layout = QHBoxLayout(self._view_bar)
        self._view_bar_layout.setContentsMargins(6, 2, 6, 2)
        self._view_bar_layout.setSpacing(10)

        # map: id -> label
        opt_defs = {
            "description": "Description",
            "videos":      "Videos",
            "layout":      "Layout",
            "downloads":   "Downloads",
            "resources":   "Additional Resources",
            "fmea":        "FMEA",
            "testing":     "Testing",
        }
        self._opt_checks = {}
        self._opt_visibility = {}

        # Build the checkbox row exactly once here.
        from functools import partial
        optional_names = ["Description", "Videos", "Layout", "Downloads", "Resources", "FMEA", "Testing"]
        for name in optional_names:
            cb = QCheckBox(name, self._view_bar)
            # Default visible unless later overridden by _set_optional_checkboxes_from_html()
            cb.setChecked(True)
            # Connect once; use partial to avoid late-binding issues in lambdas
            cb.toggled.connect(partial(self._on_toggle_optional, name))
            self._view_bar_layout.addWidget(cb)
            self._opt_checks[name] = cb
            self._opt_visibility[name] = True

        self._view_bar_layout.addStretch(1)
        outer.addWidget(self._view_bar)

        # ---------- Forms tabs ----------
        self.forms = QTabWidget(self)
        self.forms.setMinimumHeight(320)
        self.forms.currentChanged.connect(self._on_forms_current_changed)  # remember focus
        outer.addWidget(self.forms)
        
        self._init_debug_window()

        # Default visible content so the area isn't blank
        self._clear_forms()
        placeholder = QWidget()
        vbox = QVBoxLayout(placeholder)
        lbl = QLabel("No file loaded. Select a collection or board HTML page.")
        lbl.setAlignment(Qt.AlignCenter)
        vbox.addWidget(lbl)
        self.forms.addTab(placeholder, "Forms")

        # ---------- Remember last selected indices ----------
        self._last_main_tab_index = 0
        self._last_meta_sub_index = 0  # used when Metadata sub-tabs exist

        # ---------- Debounce timer: sync forms -> editor after idle ----------
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(700)  # ms
        self._debounce.timeout.connect(self._sync_forms_to_editor)

        # ---------- Periodic safety sync ----------
        self._periodic = QTimer(self)
        self._periodic.setInterval(30_000)  # 30s
        self._periodic.timeout.connect(self._sync_forms_to_editor)
        self._periodic.start()
        
        # end of __init__
        self.current_path = None
        self.current_type = "other"
        self._update_view_bar_for_path(None)

    # ---------- Public API ----------
    def load_html_file(self, path: Path):
        self.current_path = Path(path)
        self._update_view_bar_for_path(path)
        try:
            html_text = self.current_path.read_text(encoding="utf-8") if self.current_path.exists() else ""
        except Exception:
            html_text = ""

        # Build services (best effort)
        try:
            self.templates = Templates(self.ctx.templates_dir)
            self.htmlsvc = HtmlService(self.templates)
        except Exception:
            self.templates = None
            self.htmlsvc = None

        # Detect type
        if self._is_collection_file(self.current_path):
            ftype = 'collection'
        elif self._is_board_file(self.current_path):
            ftype = 'board'
        else:
            ftype = 'other'
        self.current_type = ftype
        self.typeChanged.emit(ftype)

        # Build appropriate forms
        self._clear_forms()
        if ftype == 'collection':
            self._build_collection_forms()
            self._populate_collection_forms(html_text)
        elif ftype == 'board':
            self._build_board_forms()
            self._populate_board_forms(html_text)
        else:
            w = QWidget()
            v = QVBoxLayout(w)
            v.addWidget(QLabel("Unsupported file type. Use XX.html / XXX.html (collection) or XXX-XX.html / XXX-XXX.html (board)."))
            self.forms.addTab(w, "Info")

        self._restore_focus_after_build()
        self._apply_optional_visibility()

    # ---------- Type detection ----------
    def _is_collection_file(self, path: Path) -> bool:
        if path.suffix.lower() != ".html":
            return False
        stem = path.stem
        return len(stem) in (2, 3)

    def _is_board_file(self, path: Path) -> bool:
        if path.suffix.lower() != ".html":
            return False
        return re.fullmatch(r"[A-Za-z0-9]{3}-[A-Za-z0-9]{2,3}", path.stem) is not None

    # ---------- Collection ----------
    def _build_collection_forms(self):
        # --- Metadata ---
        meta_w = QWidget()
        form = QFormLayout(meta_w)
        self.c_title = QLineEdit()
        self.c_slogan = QLineEdit()
        self.c_keywords = QLineEdit()
        self.c_description = QLineEdit()
        form.addRow("Title:", self.c_title)
        form.addRow("Slogan:", self.c_slogan)
        form.addRow("Keywords (CSV):", self.c_keywords)
        form.addRow("Description:", self.c_description)
        self.forms.addTab(meta_w, "Metadata")

        # --- Collection Table (editable PN/Title/URL/Pieces) ---
        table_w = QWidget()
        tv = QVBoxLayout(table_w)
        self.col_table = QTableWidget(0, 4, self)
        self.col_table.setHorizontalHeaderLabels(["Part No", "Title", "URL", "Pieces per Panel"])
        self.col_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        tv.addWidget(self.col_table)
        hb_tbl = QHBoxLayout()
        self.btn_tbl_add_above = QPushButton("Add Above")
        self.btn_tbl_add_below = QPushButton("Add Below")
        self.btn_tbl_del = QPushButton("Delete")
        hb_tbl.addWidget(self.btn_tbl_add_above)
        hb_tbl.addWidget(self.btn_tbl_add_below)
        hb_tbl.addWidget(self.btn_tbl_del)
        tv.addLayout(hb_tbl)
        self.forms.addTab(table_w, "Collection Table")

        # --- hooks → autosync (debounced) ---
        self.c_title.textChanged.connect(self._schedule_sync)
        self.c_slogan.textChanged.connect(self._schedule_sync)
        self.c_keywords.textChanged.connect(self._schedule_sync)
        self.c_description.textChanged.connect(self._schedule_sync)

        self.col_table.cellChanged.connect(lambda *_: self._schedule_sync())
        self.btn_tbl_add_above.clicked.connect(lambda: (self._table_insert(self.col_table, -1), self._schedule_sync()))
        self.btn_tbl_add_below.clicked.connect(lambda: (self._table_insert(self.col_table, +1), self._schedule_sync()))
        self.btn_tbl_del.clicked.connect(lambda: (self._table_delete(self.col_table), self._schedule_sync()))

    def _populate_collection_forms(self, html_text: str):
        # Fill SEO fields + Collection Table grid from the page <table>
        try:
            cm = self._block_form_signals()
        except Exception:
            from contextlib import nullcontext
            cm = nullcontext()

        with cm:
            title = slogan = keywords_csv = description = ""
            rows_for_grid: list[tuple[str, str, str, str]] = []

            soup = None
            if BeautifulSoup:
                try:
                    soup = BeautifulSoup(html_text or "", "html.parser")
                except Exception:
                    soup = None

            if soup:
                try:
                    title = soup.title.get_text(strip=True) if soup.title else ""
                    sl = soup.select_one("header .slogan")
                    slogan = sl.get_text(strip=True) if sl else ""
                    mk = soup.find("meta", attrs={"name": "keywords"})
                    md = soup.find("meta", attrs={"name": "description"})
                    keywords_csv = mk.get("content", "") if mk else ""
                    description = md.get("content", "") if md else ""

                    table = (soup.select_one("main table") or soup.find("table"))
                    if table:
                        tbody = table.find("tbody")
                        if tbody:
                            for tr in tbody.find_all("tr"):
                                tds = tr.find_all("td")
                                if not tds:
                                    continue
                                pn = tds[0].get_text(strip=True) if len(tds) >= 1 else ""
                                title_txt, href = "", ""
                                if len(tds) >= 2:
                                    a = tds[1].find("a")
                                    if a:
                                        title_txt = a.get_text(strip=True)
                                        href = (a.get("href") or "").strip()
                                    else:
                                        title_txt = tds[1].get_text(strip=True)
                                pieces = tds[2].get_text(strip=True) if len(tds) >= 3 else ""
                                rows_for_grid.append((pn, title_txt, href, pieces))
                except Exception:
                    pass

            if not title:
                m = re.search(r"(?is)<title>(.*?)</title>", html_text or "")
                title = (m.group(1).strip() if m else "")

            # Apply to widgets
            self.c_title.setText(title)
            self.c_slogan.setText(slogan)
            self.c_keywords.setText(keywords_csv)
            self.c_description.setText(description)

            self.col_table.setRowCount(0)
            for pn, title_txt, href, pieces in rows_for_grid:
                r = self.col_table.rowCount()
                self.col_table.insertRow(r)
                self.col_table.setItem(r, 0, QTableWidgetItem(pn))
                self.col_table.setItem(r, 1, QTableWidgetItem(title_txt))
                self.col_table.setItem(r, 2, QTableWidgetItem(href))
                self.col_table.setItem(r, 3, QTableWidgetItem(pieces))

    def _render_collection_html(self, html: str) -> str:
        """
        Collection write-back with editable table support:
        - Update <title>, meta keywords/description, and header slogan (regex, minimal surgery)
        - Remove any legacy <ul class="collection-links"> blocks
        - Replace ONLY the first table's <tbody> (prefer table inside <main>) with rows from 'Collection Table'
        """
        title = self.c_title.text().strip()
        keywords_csv = self.c_keywords.text().strip()
        description = self.c_description.text().strip()
        slogan = self.c_slogan.text().strip()

        # 1) <title>
        if re.search(r"(?is)<title>.*?</title>", html):
            html = re.sub(r"(?is)<title>.*?</title>", f"<title>{title}</title>", html, count=1)
        else:
            html = re.sub(r"(?is)</head>", f"<title>{title}</title></head>", html, count=1)

        # 2) metas
        def upsert_meta(h, name, val):
            pat = rf'(?is)<meta[^>]+name=["\\\']{name}["\\\'][^>]*>'
            if re.search(pat, h):
                h = re.sub(
                    rf'(?is)(<meta[^>]+name=["\\\']{name}["\\\'][^>]*content=["\\\'])[^"\']*((["\\\']))',
                    rf'\\1' + re.escape(val) + r'\2',
                    h,
                    count=1,
                )
            else:
                h = re.sub(r"(?is)</head>", f'<meta name="{name}" content="{val}"></head>', h, count=1)
            return h
        html = upsert_meta(html, "keywords", keywords_csv)
        html = upsert_meta(html, "description", description)

        # 3) slogan (only replace existing)
        html = re.sub(
            r'(?is)(<p[^>]*class="[^"]*\bslogan\b[^"]*"[^>]*>)(.*?)(</p>)',
            r"\1" + re.escape(slogan) + r"\3",
            html,
            count=1,
        )

        # 4) Remove legacy ULs
        html = re.sub(
            r'(?is)<ul[^>]*class="[^"]*\bcollection-links\b[^"]*"[^>]*>.*?</ul>',
            "",
            html,
            count=0,
        )

        # 5) Build new tbody from the editable grid
        rows = []
        for r in range(self.col_table.rowCount()):
            def cell(c):
                it = self.col_table.item(r, c)
                return (it.text().strip() if it else "")
            pn = cell(0)
            title_txt = cell(1)
            href = cell(2)
            pieces = cell(3)
            if not (pn or title_txt or href or pieces):
                continue
            rows.append((pn, title_txt, href, pieces))

        # Dedupe by PN (keep first)
        seen = set(); cleaned = []
        for pn, title_txt, href, pieces in rows:
            key = pn.strip()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            cleaned.append((pn, title_txt, href, pieces))

        def build_tbody_html(items):
            out = ["<tbody>\n"]
            for pn, title_txt, href, pieces in items:
                out.append("  <tr>\n")
                out.append(f"    <td>{pn}</td>\n")
                if href:
                    out.append(f'    <td><a href="{href}">{title_txt}</a></td>\n')
                else:
                    out.append(f"    <td>{title_txt}</td>\n")
                out.append(f"    <td>{pieces}</td>\n")
                out.append("  </tr>\n")
            out.append("</tbody>")
            return "".join(out)

        new_tbody = build_tbody_html(cleaned)

        # 6) Replace ONLY the first <tbody>…</tbody>, preferring the table inside <main>
        replaced = False
        m_main = re.search(r"(?is)(<main\b[^>]*>)(.*?)(</main>)", html)
        if m_main:
            main_inner = m_main.group(2)
            new_main_inner, n = re.subn(r"(?is)<tbody\s*>.*?</tbody>", new_tbody, main_inner, count=1)
            if n > 0:
                html = html[:m_main.start(2)] + new_main_inner + html[m_main.end(2):]
                replaced = True
        if not replaced:
            html, _ = re.subn(r"(?is)<tbody\s*>.*?</tbody>", new_tbody, html, count=1)

        return html

    # ---------- Board ----------
    def _build_board_forms(self):
        # Metadata (sub-tabs)
        self.meta_tab = QTabWidget(self)

        # -------------------- Basics --------------------
        basics = QWidget()
        vbx = QVBoxLayout(basics)

        form = QFormLayout()
        vbx.addLayout(form)

        self.in_pn = QLineEdit()
        self.in_title = QLineEdit()
        self.in_board_size = QLineEdit()
        self.in_pieces = QLineEdit()
        self.in_panel_size = QLineEdit()

        form.addRow("PN:", self.in_pn)
        form.addRow("Title:", self.in_title)
        form.addRow("Board Size:", self.in_board_size)
        form.addRow("Pieces per Panel:", self.in_pieces)
        form.addRow("Panel Size:", self.in_panel_size)  # only once

        # (Removed: Optional Tabs (Status) group)

        self.meta_tab.addTab(basics, "Basics")

        # -------------------- SEO --------------------
        seo = QWidget()
        sform = QFormLayout(seo)
        self.in_slogan = QLineEdit()
        self.in_keywords = QLineEdit()
        self.in_description = QLineEdit()
        sform.addRow("Slogan:", self.in_slogan)
        sform.addRow("Keywords (CSV):", self.in_keywords)
        sform.addRow("Description:", self.in_description)
        self.meta_tab.addTab(seo, "SEO")

        # -------------------- Navigation --------------------
        navw = QWidget()
        vbox = QVBoxLayout(navw)
        self.nav_list = QListWidget()
        self.nav_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.nav_list.customContextMenuRequested.connect(self._on_nav_context_menu)
        hb = QHBoxLayout()
        self.btn_nav_add = QPushButton("Add")
        self.btn_nav_del = QPushButton("Delete")
        hb.addWidget(self.btn_nav_add)
        hb.addWidget(self.btn_nav_del)
        vbox.addWidget(self.nav_list)
        vbox.addLayout(hb)
        self.meta_tab.addTab(navw, "Navigation")

        self.btn_nav_add.clicked.connect(lambda: (self.nav_list.addItem("Text | /path"), self._schedule_sync()))
        self.btn_nav_del.clicked.connect(lambda: (self._nav_del(), self._schedule_sync()))
        self.nav_list.model().dataChanged.connect(lambda *_: self._schedule_sync())

        # -------------------- Revisions --------------------
        revw = QWidget()
        rv = QVBoxLayout(revw)
        self.rev_table = QTableWidget(0, 4, self)
        self.rev_table.setHorizontalHeaderLabels(["Date", "Rev", "Description", "By"])
        self.rev_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        rv.addWidget(self.rev_table)
        hb2 = QHBoxLayout()
        self.btn_rev_add_above = QPushButton("Add Above")
        self.btn_rev_add_below = QPushButton("Add Below")
        self.btn_rev_del = QPushButton("Delete")
        hb2.addWidget(self.btn_rev_add_above)
        hb2.addWidget(self.btn_rev_add_below)
        hb2.addWidget(self.btn_rev_del)
        rv.addLayout(hb2)
        self.meta_tab.addTab(revw, "Revisions")

        self.btn_rev_add_above.clicked.connect(lambda: (self._rev_insert(-1), self._schedule_sync()))
        self.btn_rev_add_below.clicked.connect(lambda: (self._rev_insert(+1), self._schedule_sync()))
        self.btn_rev_del.clicked.connect(lambda: (self._rev_delete(), self._schedule_sync()))
        self.rev_table.cellChanged.connect(lambda _r, _c: self._schedule_sync())

        # -------------------- EAGLE Exports --------------------
        eaw = QWidget()
        ev = QVBoxLayout(eaw)
        self.lbl_exports = QLabel("Netlist / Partlist / Pin Interface (from ../md/PN-REV_sch.md):")
        self.exports_text = QPlainTextEdit()
        self.exports_text.setReadOnly(True)
        self.btn_reload_exports = QPushButton("Reload from md")
        self.btn_reload_exports.clicked.connect(self._reload_exports_from_md)
        ev.addWidget(self.lbl_exports)
        ev.addWidget(self.exports_text)
        ev.addWidget(self.btn_reload_exports)
        self.meta_tab.addTab(eaw, "EAGLE Exports")

        # Attach Metadata to main forms
        self.forms.addTab(self.meta_tab, "Metadata")

        # -------------------- Description --------------------
        w = QWidget()
        v = QVBoxLayout(w)
        hb = QHBoxLayout()
        self.btn_edit_seeds = QPushButton("Edit AI Seeds…")
        self.btn_edit_seeds.clicked.connect(self._on_edit_ai_seeds)
        self.cmb_maturity = QComboBox()
        self.cmb_maturity.addItems(["Placeholder", "Immature", "Mature", "Locked"])
        hb.addWidget(self.btn_edit_seeds)
        hb.addWidget(QLabel("Maturity:"))
        hb.addWidget(self.cmb_maturity)
        hb.addStretch(1)
        self.txt_description = QTextEdit()
        v.addLayout(hb)
        v.addWidget(self.txt_description)
        self.forms.addTab(w, "Description")

        for w in (self.in_pn, self.in_title, self.in_board_size, self.in_pieces, self.in_panel_size,
                self.in_slogan, self.in_keywords, self.in_description):
            w.textChanged.connect(self._schedule_sync)

        # -------------------- Videos --------------------
        w = QWidget()
        v = QVBoxLayout(w)
        self.videos_list = ReorderableList()
        self.videos_list.itemsReordered.connect(self._schedule_sync)
        hb = QHBoxLayout()
        self.btn_vid_add = QPushButton("Add URL")
        # Example default embed placeholder:
        self.btn_vid_del = QPushButton("Delete")
        hb.addWidget(self.btn_vid_add)
        hb.addWidget(self.btn_vid_del)
        hb.addStretch(1)
        v.addWidget(self.videos_list)
        v.addLayout(hb)
        self.forms.addTab(w, "Videos")
        self.btn_vid_add.clicked.connect(lambda: (self.videos_list.addItem("https://www.youtube.com/embed/..."), self._schedule_sync()))
        self.btn_vid_del.clicked.connect(lambda: (self._list_delete(self.videos_list), self._schedule_sync()))
        self.videos_list.model().dataChanged.connect(lambda *_: self._schedule_sync())
        self.videos_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.videos_list.customContextMenuRequested.connect(
            lambda pos: self._on_url_list_context(self.videos_list, "Videos", pos)
        )

        # -------------------- Schematic --------------------
        w = QWidget()
        page_layout = QVBoxLayout(w); page_layout.setContentsMargins(0, 0, 0, 0); page_layout.setSpacing(0)
        self.schematic_container = QVBoxLayout(); self.schematic_container.setContentsMargins(0, 0, 0, 0); self.schematic_container.setSpacing(0)
        page_layout.addLayout(self.schematic_container)
        self.forms.addTab(w, "Schematic")

        # -------------------- Layout --------------------
        w = QWidget()
        page_layout = QVBoxLayout(w); page_layout.setContentsMargins(0, 0, 0, 0); page_layout.setSpacing(0)
        self.layout_container = QVBoxLayout(); self.layout_container.setContentsMargins(0, 0, 0, 0); self.layout_container.setSpacing(0)
        page_layout.addLayout(self.layout_container)
        self.forms.addTab(w, "Layout")

        # -------------------- Downloads --------------------
        w = QWidget()
        v = QVBoxLayout(w)
        self.downloads_list = QListWidget()
        self.downloads_list.setDisabled(True)
        hb = QHBoxLayout()
        self.btn_dl_config = QPushButton("Configure…")
        hb.addWidget(self.btn_dl_config); hb.addStretch(1)
        v.addWidget(self.downloads_list); v.addLayout(hb)
        self.forms.addTab(w, "Downloads")

        self._downloads_state = {"datasheet": True, "ltspice": True, "gerbers": False, "cad": False, "rev": ""}
        self.btn_dl_config.clicked.connect(self._open_downloads_dialog)

        # -------------------- Datasheets --------------------
        w = QWidget()
        v = QVBoxLayout(w)
        if QWebEngineView:
            self.pdf_view = QWebEngineView()
            v.addWidget(self.pdf_view)
        else:
            self.pdf_view = None
            v.addWidget(QLabel("QtWebEngine not available."))
        self.forms.addTab(w, "Datasheets")

        # -------------------- Resources --------------------
        w = QWidget()
        v = QVBoxLayout(w)
        self.resources_list = ReorderableList()
        self.resources_list.itemsReordered.connect(self._schedule_sync)
        hb = QHBoxLayout()
        self.btn_res_add = QPushButton("Add URL")
        self.btn_res_del = QPushButton("Delete")
        hb.addWidget(self.btn_res_add); hb.addWidget(self.btn_res_del); hb.addStretch(1)
        v.addWidget(self.resources_list); v.addLayout(hb)
        self.forms.addTab(w, "Resources")
        self.btn_res_add.clicked.connect(lambda: (self.resources_list.addItem("https://www.youtube.com/embed/..."), self._schedule_sync()))
        self.btn_res_del.clicked.connect(lambda: (self._list_delete(self.resources_list), self._schedule_sync()))
        self.resources_list.model().dataChanged.connect(lambda *_: self._schedule_sync())
        self.resources_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.resources_list.customContextMenuRequested.connect(
            lambda pos: self._on_url_list_context(self.resources_list, "Resources", pos)
        )

        # -------------------- FMEA --------------------
        self._init_fmea_tab()  # lives in a method; keeps class scope clean

        # -------------------- Testing --------------------
        w = QWidget()
        v = QVBoxLayout(w)
        self.testing_table = QTableWidget(0, 7, self)
        self.testing_table.setHorizontalHeaderLabels([
            "Test No.", "Test Name", "Test Description", "Lower Limit", "Target Value", "Upper Limit", "Units"
        ])
        v.addWidget(self.testing_table)
        hb = QHBoxLayout()
        self.btn_test_add_above = QPushButton("Add Above")
        self.btn_test_add_below = QPushButton("Add Below")
        self.btn_test_del = QPushButton("Delete")
        hb.addWidget(self.btn_test_add_above); hb.addWidget(self.btn_test_add_below); hb.addWidget(self.btn_test_del)
        v.addLayout(hb)
        self.forms.addTab(w, "Testing")
        self.btn_test_add_above.clicked.connect(lambda: (self._table_insert(self.testing_table, -1), self._schedule_sync()))
        self.btn_test_add_below.clicked.connect(lambda: (self._table_insert(self.testing_table, +1), self._schedule_sync()))
        self.btn_test_del.clicked.connect(lambda: (self._table_delete(self.testing_table), self._schedule_sync()))
        self.testing_table.cellChanged.connect(lambda _r, _c: self._schedule_sync())

        # --- DIAG START: form builder ---
        try:
            def _has(name): return hasattr(self, name)
            print("[DIAG form] built:",
                "meta_title:", _has("meta_title"),
                "in_title:", _has("in_title"),
                "board_pn:", _has("board_pn"),
                "in_pn:", _has("in_pn"),
                "panel_pieces:", _has("panel_pieces"),
                "in_pieces:", _has("in_pieces"))
            import sys; sys.stdout.flush()
        except Exception as _e:
            print("[DIAG form] print failed:", _e)
        # --- DIAG END: form builder ---

        # IMPORTANT: Do NOT call _wire_optional_checkboxes() here
        # if you've already wired the top bar in __init__.


    def _populate_board_forms(self, html_text: str):
        with self._block_form_signals():
            # Parse with BeautifulSoup, fallback to regex
            pn, title = "", ""
            slogan, keywords_csv, description = "", "", ""
            details = {"Board Size": "", "Pieces per Panel": "", "Panel Size": ""}
            nav: list[tuple[str, str]] = []
            revs: list[tuple[str, str, str, str]] = []
            schem_imgs: list[str] = []
            layout_imgs: list[str] = []
            downloads: list[tuple[str, str]] = []
            videos: list[str] = []
            resources: list[str] = []
            datasheet = ""

            soup = None
            if BeautifulSoup:
                try:
                    soup = BeautifulSoup(html_text or "", "html.parser")
                except Exception:
                    soup = None

            # PN & Title
            if soup and soup.title:
                ttl = soup.title.get_text(strip=True)
                m = re.match(r"\s*([A-Za-z0-9\-]+)\s*\|\s*(.+)$", ttl)
                if m:
                    pn, title = m.group(1).strip(), m.group(2).strip()
            if not title and soup:
                h1 = soup.select_one("header h1")
                if h1:
                    m2 = re.match(r"\s*([A-Za-z0-9\-]+)\s*[–-]\s*(.+)$", h1.get_text(strip=True))
                    if m2:
                        pn = pn or m2.group(1).strip()
                        title = m2.group(2).strip()
                    else:
                        title = h1.get_text(strip=True)
            if not pn and self.current_path:
                stem = self.current_path.stem
                if "-" in stem:
                    pn = stem.split("-")[0].strip()

            # Reflect file's current sections into the optional-tab checkboxes
            self._set_optional_checkboxes_from_html(html_text)

            # SEO
            if soup:
                sl = soup.select_one("header .slogan")
                slogan = sl.get_text(strip=True) if sl else ""
                mk = soup.find("meta", attrs={"name": "keywords"})
                md = soup.find("meta", attrs={"name": "description"})
                keywords_csv = mk.get("content", "") if mk else ""
                description = md.get("content", "") if md else ""

            # Body Description (#description → join <p> into paragraphs with blank lines)
            body_desc_text = ""
            if soup:
                desc_div = soup.select_one("#description")
                if desc_div:
                    ps = desc_div.find_all("p")
                    if ps:
                        body_desc_text = "\n\n".join(p.get_text("\n", strip=True) for p in ps)
                    else:
                        # If no <p>, use raw text under the div (skip bare <h2>Description>)
                        raw = desc_div.get_text("\n", strip=True)
                        if raw and raw.strip().lower() != "description":
                            body_desc_text = raw

            # Details
            if soup:
                details_div = soup.select_one("#details")
                if details_div:
                    for ptag in details_div.find_all("p"):
                        strong = ptag.find("strong")
                        if strong:
                            label = strong.get_text(strip=True).rstrip(":")
                            value = ptag.get_text(strip=True).replace(strong.get_text(strip=True), "").strip(" :")
                            details[label] = value

            # Nav
            if soup:
                for a in soup.select("nav .nav-links a"):
                    nav.append((a.get_text(strip=True), a.get("href", "")))

            # Revisions
            if soup:
                table = soup.select_one("#revisions table, table.revisions-table")
                if table:
                    for tr in table.find_all("tr"):
                        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
                        if len(tds) >= 4:
                            revs.append((tds[0], tds[1], tds[2], tds[3]))

            # Images (relative paths extracted)
            if soup:
                schem_imgs = [img.get("src", "").strip() for img in soup.select("#schematic img") if img.get("src")]
                layout_imgs = [img.get("src", "").strip() for img in soup.select("#layout img") if img.get("src")]

            # Downloads (read what's actually there)
            if soup:
                for a in soup.select("#downloads .download-list a"):
                    downloads.append((a.get_text(strip=True), a.get("href", "")))
            for text, url in downloads:
                if url.lower().endswith(".pdf"):
                    datasheet = url
                    break
            if not datasheet and pn:
                datasheet = f"../datasheets/{pn}.pdf"

            # Videos/Resources (scoped parsing; do NOT cross-populate)
            videos, resources = [], []
            if soup:
                # Only iframes under #videos
                videos_div = soup.select_one('#videos')
                if videos_div:
                    for ifr in videos_div.find_all('iframe'):
                        src = (ifr.get('src') or '').strip()
                        if 'youtube.com/embed' in src:
                            videos.append(src)

                # Only iframes under #resources
                resources_div = soup.select_one('#resources')
                if resources_div:
                    for ifr in resources_div.find_all('iframe'):
                        src = (ifr.get('src') or '').strip()
                        if 'youtube.com/embed' in src:
                            resources.append(src)

                # Dedupe (preserve order) within each section
                def _dedupe(seq):
                    seen = set(); out = []
                    for s in seq:
                        if s not in seen:
                            seen.add(s); out.append(s)
                    return out
                videos = _dedupe(videos)
                resources = _dedupe(resources)

            # ---------- Apply to widgets ----------
            if hasattr(self, "txt_description"):
                self.txt_description.setPlainText(body_desc_text)

            self.in_pn.setText(pn)
            self.in_title.setText(title)
            self.in_board_size.setText(details.get("Board Size", ""))
            self.in_pieces.setText(details.get("Pieces per Panel", ""))
            self.in_panel_size.setText(details.get("Panel Size", ""))
            self.in_slogan.setText(slogan)
            self.in_keywords.setText(keywords_csv)
            self.in_description.setText(description)

            self.nav_list.clear()
            for text, url in nav:
                self.nav_list.addItem(f"{text} | {url}")

            self.rev_table.setRowCount(0)
            for row in revs:
                i = self.rev_table.rowCount()
                self.rev_table.insertRow(i)
                for c, val in enumerate(row[:4]):
                    self.rev_table.setItem(i, c, QTableWidgetItem(val))

            # Exports preview
            self._reload_exports_from_md()

            # ---------- Schematic & Layout viewers (absolute paths, no helpers required) ----------
            def _abs_from_rel(rel: str) -> str:
                if not rel:
                    return ""
                rl = rel.strip()
                if rl.startswith(("http://", "https://", "file:")):
                    return rl
                try:
                    return str((self.current_path.parent / rl).resolve())
                except Exception:
                    return ""

            # Schematic: take first image if any
            schem_path_abs = _abs_from_rel(schem_imgs[0]) if schem_imgs else ""
            self._place_image_in_container(self.schematic_container, schem_path_abs, "IMAGE NOT FOUND")

            # Layout: take first image if any
            layout_path_abs = _abs_from_rel(layout_imgs[0]) if layout_imgs else ""
            self._place_image_in_container(self.layout_container, layout_path_abs, "IMAGE NOT FOUND")

            # ---- Downloads: derive state EXACTLY from HTML, infer REV from links, then normalize preview ----
            pn_now = self.in_pn.text().strip()
            has_datasheet = any(("/datasheets/" in u) and u.lower().endswith(".pdf") for _, u in downloads)
            has_ltspice   = any(("/ltspice/"   in u) and u.lower().endswith(".asc") for _, u in downloads)
            has_gerbers   = any(("/gerbers/"   in u) and u.lower().endswith(".zip") for _, u in downloads)
            has_cad       = any(("/cad/eagle-6-3/" in u) and u.lower().endswith(".zip") for _, u in downloads)

            rev_from_links = self._infer_rev_from_downloads(pn_now, downloads)
            rev_now = rev_from_links or self._latest_rev_from_ui()

            state = {
                "datasheet": has_datasheet,
                "ltspice":   has_ltspice,
                "gerbers":   has_gerbers,
                "cad":       has_cad,
                "rev":       rev_now,
            }
            self._downloads_state = state

            # normalize preview to our computed state/URLs
            self.downloads_list.clear()
            for text, href in self._downloads_items_from_state(pn_now, rev_now, state):
                self.downloads_list.addItem(f"{text} | {href}")

            # Videos/Resources lists
            self.videos_list.clear()
            for url in videos:
                self.videos_list.addItem(url)
            self.resources_list.clear()
            for url in resources:
                self.resources_list.addItem(url)

            # Datasheet (PDF view if available)
            if getattr(self, "pdf_view", None) is not None and datasheet:
                try:
                    ds = datasheet
                    if not (ds.startswith("http://") or ds.startswith("https://") or ds.startswith("file:")):
                        base = self.current_path.parent.resolve()
                        ds_path = (base / ds).resolve()
                        self.pdf_view.load(QUrl.fromLocalFile(str(ds_path)))
                    else:
                        self.pdf_view.load(QUrl(ds))
                except Exception:
                    pass

    # ---------- Sync engine ----------
    def _schedule_sync(self):
        if self._suppress_form_signals:
            return
        self._debounce.start()

    def _sync_forms_to_editor(self):
        # Get current editor html
        getter = self.get_editor_text if callable(self.get_editor_text) else None
        html = getter() if getter else ""
        if not html:
            return

        # Render from forms
        if self.current_type == "collection":
            new_html = self._render_collection_html(html)
        elif self.current_type == "board":
            new_html = self._render_board_html(html)
        else:
            return

        # Only set text if there is a *real* change
        if new_html and new_html != html:
            self._set_editor_text(new_html)

#     # ---------- Renderers (writeback) ----------
#     def _render_collection_html(self, html: str) -> str:
#         title = self.c_title.text().strip()
#         slogan = self.c_slogan.text().strip()
#         keywords_csv = self.c_keywords.text().strip()
#         description = self.c_description.text().strip()

#         links = []
#         for r in range(self.collection_table.rowCount()):
#             t = self.collection_table.item(r, 0)
#             u = self.collection_table.item(r, 1)
#             links.append(((t.text().strip() if t else ""), (u.text().strip() if u else "")))

#         soup = None
#         if BeautifulSoup:
#             try:
#                 soup = BeautifulSoup(html, "html.parser")
#             except Exception:
#                 soup = None

#         if soup:
#             # <title>
#             if soup.title is None:
#                 head = soup.head or soup.new_tag("head")
#                 if soup.head is None:
#                     soup.html.insert(0, head)
#                 title_tag = soup.new_tag("title")
#                 title_tag.string = title
#                 head.append(title_tag)
#             else:
#                 soup.title.string = title

#             # meta tags
#             def set_meta(name, val):
#                 tag = soup.find("meta", attrs={"name": name})
#                 if tag is None:
#                     tag = soup.new_tag("meta")
#                     tag["name"] = name
#                     if soup.head is None:
#                         soup.html.insert(0, soup.new_tag("head"))
#                     soup.head.append(tag)
#                 tag["content"] = val
#             set_meta("keywords", keywords_csv)
#             set_meta("description", description)

#             # slogan in header
#             header = soup.find("header") or soup.new_tag("header")
#             if header.parent is None and soup.body:
#                 soup.body.insert(0, header)
#             slog = header.find(class_="slogan")
#             if slog is None:
#                 slog = soup.new_tag("p", **{"class": "slogan"})
#                 header.append(slog)
#             slog.string = slogan

#             # Links under <main> as UL
#             main = soup.find("main")
#             if main is None and soup.body:
#                 main = soup.new_tag("main")
#                 soup.body.append(main)
#             # remove existing anchors (conservative: in ul.collection-links)
#             for ul in main.select("ul.collection-links"):
#                 ul.decompose()
#             ul = soup.new_tag("ul", **{"class": "collection-links"})
#             for text, url in links:
#                 li = soup.new_tag("li")
#                 a = soup.new_tag("a", href=url)
#                 a.string = text
#                 li.append(a)
#                 ul.append(li)
#             main.append(ul)

#             return str(soup)

#         # Fallback (no soup): naive <title> and metas
#         new_html = html
#         if "<title>" in new_html:
#             new_html = re.sub(r"(?is)<title>.*?</title>", f"<title>{title}</title>", new_html)
#         else:
#             new_html = new_html.replace("</head>", f"<title>{title}</title></head>")
#         def upsert_meta(name, val):
#             pattern = rf'(?is)<meta[^>]+name=["\\\']{name}["\\\'][^>]*>'
#             if re.search(pattern, new_html):
#                 return re.sub(rf'(?is)(<meta[^>]+name=["\\\']{name}["\\\'][^>]*content=["\\\']).*?(["\\\'])',
#                               rf'\1{val}\2', new_html)
#             return new_html.replace("</head>", f'<meta name="{name}" content="{val}"></head>')
#         new_html = upsert_meta("keywords", keywords_csv)
#         new_html = upsert_meta("description", description)
#         return new_html

    def _html_escape(self, s: str) -> str:
        s = s or ""
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _replace_table_tbody(self, html: str, table_class: str, rows: list[tuple]) -> str:
        """
        Replace ONLY the first <tbody>…</tbody> of the first <table class="table_class">.
        Preserves existing <thead>. Produces pretty, indented <tbody>.
        Idempotent: if generated tbody equals current tbody (ignoring trivial whitespace), do nothing.
        """
        # 0) remove fully-empty UI rows (prevents “growth” via blank lines)
        clean_rows = []
        for row in rows:
            if any((c or "").strip() for c in row):
                clean_rows.append(tuple("" if c is None else str(c) for c in row))
        rows = clean_rows

        # 1) find the first matching table anywhere in the doc
        m = re.search(
            rf'(?is)(<table\b[^>]*class="[^"]*\b{re.escape(table_class)}\b[^"]*"[^>]*>)(.*?)(</table>)',
            html
        )
        if not m:
            return html

        open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)

        # 2) locate its first tbody
        m_tb = re.search(r'(?is)(<tbody\b[^>]*>)(.*?)(</tbody>)', inner)
        if not m_tb:
            # If there is no <tbody>, don't create one (avoid corrupting possible complex thead layouts)
            return html

        tbody_open, tbody_inner, tbody_close = m_tb.group(1), m_tb.group(2), m_tb.group(3)

        # 3) figure indentation from where <table> starts
        table_abs_start = m.start(1)
        line_start = html.rfind("\n", 0, table_abs_start) + 1
        base_indent = html[line_start:table_abs_start]
        indent_tbl = base_indent if not base_indent.strip() else "  "
        i1 = indent_tbl + "  "   # inside <table>
        i2 = i1 + "  "           # inside thead/tbody
        i3 = i2 + "  "           # inside tr

        # 4) build new pretty tbody
        parts = []
        parts.append("<tbody>\n")
        for row in rows:
            parts.append(f"{i2}<tr>\n")
            for cell in row:
                parts.append(f"{i3}<td>{self._html_escape(cell)}</td>\n")
            parts.append(f"{i2}</tr>\n")
        parts.append(f"{i1}</tbody>")
        new_tbody = "".join(parts)

        # 5) compare normalized versions; if equal, skip replacing (idempotent)
        def _norm(s: str) -> str:
            # collapse whitespace between tags and strip
            s = re.sub(r">\s+<", "><", s.strip())
            s = re.sub(r"\s+", " ", s)
            return s

        current_tbody_full = f"{tbody_open}{tbody_inner}{tbody_close}"
        new_tbody_full     = new_tbody  # already includes open/close

        if _norm(current_tbody_full) == _norm(new_tbody_full):
            return html  # no change

        # 6) splice back this new tbody within table inner, then back into html
        inner_new = inner[:m_tb.start(1)] + new_tbody_full + inner[m_tb.end(3):]
        return html[:m.start(1)] + open_tag + inner_new + close_tag + html[m.end(3):]

    def _render_board_html(self, html: str) -> str:
        """
        Write back all Board-form edits into the current HTML and pretty-print:
        - <title>, meta keywords/description
        - Header slogan
        - #details block (Part No, Title, Board Size, Pieces per Panel, Panel Size)
        - <ul class="nav-links"> pretty
        - <table class="revisions-table"> tbody pretty
        - <table class="testing-table"> tbody pretty
        - <table class="fmea-table"> tbody pretty
        - #videos and #resources iframe lists pretty (scoped, no cross-population)
        - #downloads .download-list pretty
        - #description content (from the Description tab) as clean <p> paragraphs
        """
        import re

        # ---- gather UI values ----
        pn = self.in_pn.text().strip()
        title = self.in_title.text().strip()
        board_size = self.in_board_size.text().strip()
        pieces = self.in_pieces.text().strip()
        panel_size = self.in_panel_size.text().strip()
        slogan = self.in_slogan.text().strip()
        keywords_csv = self.in_keywords.text().strip()
        meta_description = self.in_description.text().strip()

        # Long body description from the Description tab
        long_desc = ""
        if hasattr(self, "txt_description") and self.txt_description is not None:
            long_desc = self.txt_description.toPlainText().strip()

        # nav items
        nav_items: list[tuple[str, str]] = []
        for i in range(self.nav_list.count()):
            txt = self.nav_list.item(i).text()
            if " | " in txt:
                t, u = txt.split(" | ", 1)
            else:
                t, u = txt, "#"
            nav_items.append((t.strip(), u.strip()))

        # revisions rows
        revs: list[tuple[str, str, str, str]] = []
        for r in range(self.rev_table.rowCount()):
            def rc(c):
                it = self.rev_table.item(r, c)
                return it.text().strip() if it else ""
            revs.append((rc(0), rc(1), rc(2), rc(3)))

        # testing rows
        tests: list[tuple[str, ...]] = []
        if hasattr(self, "testing_table"):
            for r in range(self.testing_table.rowCount()):
                def tc(c):
                    it = self.testing_table.item(r, c)
                    return it.text().strip() if it else ""
                tests.append((tc(0), tc(1), tc(2), tc(3), tc(4), tc(5), tc(6)))

        # fmea rows
        fmea_rows: list[tuple[str, ...]] = []
        if hasattr(self, "fmea_table"):
            for r in range(self.fmea_table.rowCount()):
                def fc(c):
                    it = self.fmea_table.item(r, c)
                    return it.text().strip() if it else ""
                fmea_rows.append((
                    fc(0), fc(1), fc(2), fc(3), fc(4), fc(5), fc(6), fc(7),
                    fc(8), fc(9), fc(10), fc(11), fc(12), fc(13), fc(14), fc(15), fc(16)
                ))

        # videos/resources urls from UI (already separated per section)
        videos_urls = [self.videos_list.item(i).text().strip() for i in range(self.videos_list.count())]
        resources_urls = [self.resources_list.item(i).text().strip() for i in range(self.resources_list.count())]

        # downloads (normalized preview state if available; else read the list)
        downloads_items: list[tuple[str, str]] = []
        if hasattr(self, "_downloads_items_from_state") and hasattr(self, "_downloads_state"):
            pn_now = pn
            rev_now = self._downloads_state.get("rev", "") if isinstance(getattr(self, "_downloads_state", None), dict) else ""
            for text, href in self._downloads_items_from_state(pn_now, rev_now, self._downloads_state):
                downloads_items.append((text, href))
        else:
            for i in range(self.downloads_list.count()):
                raw = self.downloads_list.item(i).text()
                if " | " in raw:
                    t, u = raw.split(" | ", 1)
                else:
                    t, u = raw, "#"
                downloads_items.append((t.strip(), u.strip()))

        # ---- tiny HTML helpers ----
        def _html_escape(s: str) -> str:
            return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

        def _ensure_div_in_main(soup, main, div_id: str, default_h2_text: str):
            div = soup.select_one(f"#{div_id}")
            if div is None and main is not None:
                div = soup.new_tag("div", id=div_id, **{"class": "tab-content"})
                h2 = soup.new_tag("h2"); h2.string = default_h2_text
                div.append(h2)
                main.append(div)
            return div

        def _pretty_ul_downloads(h: str, items: list[tuple[str, str]]) -> str:
            # Find the <ul class="download-list"> inside #downloads (prefer scoped)
            m_scope = re.search(r'(?is)(<div\b[^>]*id="downloads"[^>]*>)(.*?)(</div>)', h)
            region, offset = (h, 0)
            if m_scope:
                region, offset = m_scope.group(2), m_scope.start(2)
            m_ul = re.search(r'(?is)(<ul\b[^>]*class="[^"]*\bdownload-list\b[^"]*"[^>]*>)(.*?)(</ul>)', region)
            if not m_ul:
                # fallback: any download-list in doc
                m_ul = re.search(r'(?is)(<ul\b[^>]*class="[^"]*\bdownload-list\b[^"]*"[^>]*>)(.*?)(</ul>)', h)
                if not m_ul:
                    return h
                offset = 0
                region = h

            open_tag, inner, close_tag = m_ul.group(1), m_ul.group(2), m_ul.group(3)
            ul_abs_start = offset + m_ul.start(1)
            line_start = h.rfind("\n", 0, ul_abs_start) + 1
            base_indent = h[line_start:ul_abs_start]
            indent_ul = base_indent if not base_indent.strip() else "  "
            i1 = indent_ul + "  "

            out = ["\n"]
            for text_val, href_val in items:
                safe_t = _html_escape(text_val or "")
                safe_u = (href_val or "").replace("\\", "/")
                out.append(f'{i1}<li><a href="{safe_u}" rel="noopener noreferrer" target="_blank">{safe_t}</a></li>\n')
            out.append(indent_ul)
            pretty = f"{open_tag}{''.join(out)}{close_tag}"

            if m_scope and offset:
                new_region = region[:m_ul.start(1)] + pretty + region[m_ul.end(3):]
                return h[:m_scope.start(2)] + new_region + h[m_scope.end(2):]
            else:
                return h[:m_ul.start(1)] + pretty + h[m_ul.end(3):]

        def _replace_iframe_list_local(h: str, container_id: str, urls: list[str]) -> str:
            """
            Rebuild the *inside* of <div id="{container_id}"> with:
            <h2>...</h2>
            <div class="video-wrapper"><iframe ...></iframe></div> (for each url)
            Preserves the <div ...> tag itself.
            """
            m_div = re.search(rf'(?is)(<div\b[^>]*id="{re.escape(container_id)}"[^>]*>)(.*?)(</div>)', h)
            if not m_div:
                return h
            open_div, inner, close_div = m_div.group(1), m_div.group(2), m_div.group(3)

            # Detect existing indentation
            div_abs_start = m_div.start(1)
            line_start = h.rfind("\n", 0, div_abs_start) + 1
            base_indent = h[line_start:div_abs_start]
            indent_div = base_indent if not base_indent.strip() else "  "
            i1 = indent_div + "  "
            i2 = i1 + "  "

            # Preserve a sensible <h2> label
            heading_text = "Videos" if container_id == "videos" else ("Additional Resources" if container_id == "resources" else container_id.capitalize())

            out = ["\n", f"{i1}<h2>{heading_text}</h2>\n"]
            for u in urls:
                u = (u or "").strip()
                if not u:
                    continue
                out.append(f"{i1}<div class=\"video-wrapper\">\n")
                out.append(
                    f'{i2}<iframe src="{_html_escape(u)}" title="YouTube video player" width="560" height="315" '
                    f'loading="lazy" referrerpolicy="strict-origin-when-cross-origin" '
                    f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
                    f'allowfullscreen frameborder="0"></iframe>\n'
                )
                out.append(f"{i1}</div>\n")
            out.append(indent_div)

            pretty = f"{open_div}{''.join(out)}{close_div}"
            return h[:m_div.start(1)] + pretty + h[m_div.end(3):]

        def _replace_nav_ul_local(h: str, items: list[tuple[str, str]]) -> str:
            """
            Pretty print the first <ul class="nav-links"> (prefer the one under <nav>), replacing its li set.
            """
            # scope inside <nav> for the ul
            m_nav = re.search(r'(?is)(<nav\b[^>]*>)(.*?)(</nav>)', h)
            region, offset = (h, 0)
            if m_nav:
                region, offset = m_nav.group(2), m_nav.start(2)

            m_ul = re.search(r'(?is)(<ul\b[^>]*class="[^"]*\bnav-links\b[^"]*"[^>]*>)(.*?)(</ul>)', region)
            if not m_ul:
                # fallback anywhere
                m_ul = re.search(r'(?is)(<ul\b[^>]*class="[^"]*\bnav-links\b[^"]*"[^>]*>)(.*?)(</ul>)', h)
                if not m_ul:
                    return h
                offset = 0
                region = h

            open_ul, inner, close_ul = m_ul.group(1), m_ul.group(2), m_ul.group(3)

            ul_abs_start = offset + m_ul.start(1)
            line_start = h.rfind("\n", 0, ul_abs_start) + 1
            base_indent = h[line_start:ul_abs_start]
            indent_ul = base_indent if not base_indent.strip() else "  "
            i1 = indent_ul + "  "

            out = ["\n"]
            for text_val, url_val in items:
                safe_t = _html_escape(text_val or "")
                safe_u = (url_val or "").replace("\\", "/")
                out.append(f'{i1}<li><a href="{safe_u}">{safe_t}</a></li>\n')
            out.append(indent_ul)

            pretty = f"{open_ul}{''.join(out)}{close_ul}"

            if m_nav and offset:
                new_region = region[:m_ul.start(1)] + pretty + region[m_ul.end(3):]
                return h[:m_nav.start(2)] + new_region + h[m_nav.end(2):]
            else:
                return h[:m_ul.start(1)] + pretty + h[m_ul.end(3):]

        # ---- use BeautifulSoup if available for structure, then pretty-print via helpers ----
        soup = None
        if BeautifulSoup:
            try:
                soup = BeautifulSoup(html, "html.parser")
            except Exception:
                soup = None

        page_title = f"{pn} | {title}" if pn else title

        if soup:
            # <title>
            if soup.title is None:
                head = soup.head or soup.new_tag("head")
                if soup.head is None and soup.html:
                    soup.html.insert(0, head)
                t = soup.new_tag("title"); t.string = page_title
                head.append(t)
            else:
                soup.title.string = page_title

            # meta upserts
            def set_meta(name, val):
                tag = soup.find("meta", attrs={"name": name})
                if tag is None:
                    tag = soup.new_tag("meta"); tag["name"] = name
                    if soup.head is None and soup.html:
                        soup.html.insert(0, soup.new_tag("head"))
                    (soup.head or soup).append(tag)
                tag["content"] = val
            set_meta("keywords", keywords_csv)
            set_meta("description", meta_description)

            # header slogan
            header = soup.find("header") or soup.new_tag("header")
            if header.parent is None and soup.body:
                soup.body.insert(0, header)
            slog = header.find(class_="slogan")
            if slog is None:
                slog = soup.new_tag("p", **{"class": "slogan"}); header.append(slog)
            slog.string = slogan

            # details block
            main = soup.find("main")
            details_div = soup.select_one("#details")
            if details_div is None and main is not None:
                details_div = soup.new_tag("div", id="details"); main.insert(0, details_div)

            def upsert_detail(label, val):
                if not details_div:
                    return
                for ptag in details_div.find_all("p"):
                    st = ptag.find("strong")
                    if st and st.get_text(strip=True).rstrip(":").lower() == label.lower():
                        ptag.clear()
                        st2 = soup.new_tag("strong"); st2.string = f"{label}:"
                        ptag.append(st2); ptag.append(" " + val)
                        return
                ptag = soup.new_tag("p")
                st2 = soup.new_tag("strong"); st2.string = f"{label}:"
                ptag.append(st2); ptag.append(" " + val)
                details_div.append(ptag)

            upsert_detail("Part No", pn or (self.current_path.stem if self.current_path else ""))
            upsert_detail("Title", title)
            upsert_detail("Board Size", board_size)
            upsert_detail("Pieces per Panel", pieces)
            upsert_detail("Panel Size", panel_size)

            # Ensure containers exist for sections we pretty-write later
            def ensure_div(div_id: str, default_h2: str):
                return _ensure_div_in_main(soup, main, div_id, default_h2)
            ensure_div("revisions", "Revision History")
            ensure_div("videos", "Videos")
            ensure_div("resources", "Additional Resources")
            ensure_div("downloads", "Downloads")
            ensure_div("description", "Description")

            # ---- Write back the long description into #description (pretty paragraphs) ----
            desc_div = soup.select_one("#description")
            if desc_div:
                # Remove all children then rebuild heading and paragraphs
                for child in list(desc_div.children):
                    child.decompose()

                h2 = soup.new_tag("h2"); h2.string = "Description"
                desc_div.append(h2)

                if long_desc:
                    paras = re.split(r"\n\s*\n", long_desc.strip())
                    for para in paras:
                        para = para.strip()
                        if not para:
                            continue
                        p = soup.new_tag("p")
                        lines = para.split("\n")
                        for idx, ln in enumerate(lines):
                            p.append(ln)
                            if idx < len(lines) - 1:
                                p.append(soup.new_tag("br"))
                        desc_div.append(p)

            # finalize soup to string (compact), then do string-level pretty replacements
            html = str(soup)

        else:
            # Fallback without soup: minimally update <title>, metas, slogan (no structure creation)
            if re.search(r"(?is)<title>.*?</title>", html):
                html = re.sub(r"(?is)<title>.*?</title>", f"<title>{page_title}</title>", html, count=1)
            else:
                html = re.sub(r"(?is)</head>", f"<title>{page_title}</title></head>", html, count=1)

            def upsert_meta(h, name, val):
                pat = rf'(?is)<meta[^>]+name=["\\\']{name}["\\\'][^>]*>'
                if re.search(pat, h):
                    return re.sub(
                        rf'(?is)(<meta[^>]+name=["\\\']{name}["\\\'][^>]*content=["\\\'])[^"\']*(["\\\'])',
                        rf'\\1{re.escape(val)}\\2', h, count=1)
                return re.sub(r"(?is)</head>", f'<meta name="{name}" content="{val}"></head>', h, count=1)

            html = upsert_meta(html, "keywords", keywords_csv)
            html = upsert_meta(html, "description", meta_description)
            # replace existing slogan text only
            html = re.sub(
                r'(?is)(<p[^>]*class="[^"]*\bslogan\b[^"]*"[^>]*>)(.*?)(</p>)',
                r"\1" + re.escape(slogan) + r"\3",
                html, count=1
            )

            # Fallback Description write-back (regex) if #description exists
            def _fallback_desc(h: str) -> str:
                m = re.search(r'(?is)(<div\b[^>]*id="description"[^>]*>)(.*?)(</div>)', h)
                if not m:
                    return h
                def _esc(s: str) -> str:
                    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
                body = ['<h2>Description</h2>']
                if long_desc:
                    paras = re.split(r"\n\s*\n", long_desc.strip())
                    for para in paras:
                        if not para.strip():
                            continue
                        lines = [_esc(x) for x in para.split("\n")]
                        body.append(f"<p>{'<br/>'.join(lines)}</p>")
                inner_new = "\n  " + "\n  ".join(body) + "\n"
                return h[:m.start(1)] + m.group(1) + inner_new + m.group(3) + h[m.end(3):]
            html = _fallback_desc(html)

        # ---- prettify/replace specific structures (string-level, preserves tags) ----

        # Nav UL
        if hasattr(self, "_replace_nav_ul"):
            html = self._replace_nav_ul(html, nav_items)
        else:
            html = _replace_nav_ul_local(html, nav_items)

        # Tables (use your existing helper to prevent duplication/runaway growth)
        html = self._replace_table_tbody(html, "revisions-table", revs)
        if tests:
            html = self._replace_table_tbody(html, "testing-table", tests)
        if fmea_rows:
            html = self._replace_table_tbody(html, "fmea-table", fmea_rows)

        # Videos / Resources — strictly within their own containers
        if hasattr(self, "_replace_iframe_list"):
            html = self._replace_iframe_list(html, "videos", videos_urls)
            html = self._replace_iframe_list(html, "resources", resources_urls)
        else:
            html = _replace_iframe_list_local(html, "videos", videos_urls)
            html = _replace_iframe_list_local(html, "resources", resources_urls)

        # Downloads UL
        if hasattr(self, "_replace_downloads_ul"):
            html = self._replace_downloads_ul(html, downloads_items)
        else:
            html = _pretty_ul_downloads(html, downloads_items)

        # >>> Pretty-print the Description block last
        html = self._prettify_description_div(html)

        html = self._apply_optional_visibility(html)
        return html

    # ---------- Common helpers ----------
    def _clear_forms(self):
        while self.forms.count():
            w = self.forms.widget(0)
            self.forms.removeTab(0)
            if w:
                w.deleteLater()

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

    def _list_delete(self, lw: QListWidget):
        for it in lw.selectedItems():
            lw.takeItem(lw.row(it))

    def _nav_del(self):
        self._list_delete(self.nav_list)

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
        """
        Load EAGLE export markdown strictly from ../md/PN_REV_sch.md (underscore only).
        Fallback: pick the latest matching ../md/PN_*_sch.md (underscore).
        Shows the resolved path or a clear 'Not found' list.
        """
        try:
            pn = (self.in_pn.text() or "").strip()
            rev = (self._latest_rev_from_ui() or "").strip()

            if not pn or not self.current_path:
                self.exports_text.setPlainText("PN or file context missing.")
                return

            md_dir = (self.current_path.parent / ".." / "md").resolve()

            def _exists(p: Path) -> bool:
                try:
                    return p.exists()
                except Exception:
                    return False

            chosen: Path | None = None

            # Exact underscore candidate first
            if rev:
                cand = md_dir / f"{pn}_{rev}_sch.md"
                if _exists(cand):
                    chosen = cand

            # Fallback: latest PN_*_sch.md (underscore only)
            if chosen is None:
                try:
                    matches = sorted(md_dir.glob(f"{pn}_*_sch.md"))
                    if matches:
                        chosen = matches[-1]
                except Exception:
                    pass

            if chosen and _exists(chosen):
                try:
                    text = chosen.read_text(encoding="utf-8")
                    self.exports_text.setPlainText(f"# Loaded: {chosen}\n\n{text}")
                    return
                except Exception as read_err:
                    self.exports_text.setPlainText(f"Found but failed to read:\n{chosen}\n\n{read_err}")
                    return

            # Nothing found: be explicit about what we tried/expect
            tried = []
            if rev:
                tried.append(str(md_dir / f"{pn}_{rev}_sch.md"))
            tried.append(str(md_dir / f"{pn}_<REV>_sch.md"))
            msg = "Not found (underscore format only expected):\n" + "\n".join(tried)
            self.exports_text.setPlainText(msg)

        except Exception as e:
            self.exports_text.setPlainText(f"Error loading exports: {e}")

    # ---------- Editor wiring ----------
    def _find_editor(self):
        # Traverse up to locate the right-side QTabWidget and get the editor tab
        w = self.parent()
        while w is not None and not hasattr(w, 'addTab'):
            w = w.parent()
        # w is QTabWidget in MainWindow (Forms at index 0, Editor at index 1)
        if w is not None and w.count() >= 2:
            editor = w.widget(1)
            return editor
        return None

    def _set_editor_text(self, html: str):
        ed = self._find_editor()
        if ed and hasattr(ed, 'set_text'):
            ed.set_text(html)  # marks dirty; autosaver + Ctrl+S will save

    # ---------- Small context manager to block signals during populate ----------
    class _block_form_signals_ctx:
        def __init__(self, host):
            self.host = host
        def __enter__(self):
            self.host._suppress_form_signals = True
        def __exit__(self, exc_type, exc, tb):
            self.host._suppress_form_signals = False

    def _block_form_signals(self):
        return MainTabs._block_form_signals_ctx(self)
    
    def _prettify_revisions_table_in_html(self, html: str) -> str:
        """
        Force-pretty the FIRST <table class="revisions-table">…</table> anywhere in the doc.
        Preserves the exact <table ...> and </table> tags; rebuilds inner with clean newlines.
        """
        # 1) Collect rows from UI
        rows = []
        for r in range(self.rev_table.rowCount()):
            def cell(c):
                it = self.rev_table.item(r, c)
                return it.text().strip() if it else ""
            rows.append((cell(0), cell(1), cell(2), cell(3)))

        HEADERS = ["Date", "Revision", "Description", "By"]

        # 2) Find the first <table ... class="...revisions-table...">…</table>
        m = re.search(r'(?is)(<table\b[^>]*class="[^"]*\brevisions-table\b[^"]*"[^>]*>)(.*?)(</table>)', html)
        if not m:
            return html  # nothing to do

        open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)

        # 3) Determine indentation based on where the <table> starts in the original text
        table_abs_start = m.start(1)
        line_start = html.rfind("\n", 0, table_abs_start) + 1
        base_indent = html[line_start:table_abs_start]
        # If there’s other text on the same line before <table>, default to two spaces
        indent_tbl = base_indent if not base_indent.strip() else "  "

        i0 = indent_tbl          # aligns with <table> line column for </table>
        i1 = indent_tbl + "  "   # inside <table>
        i2 = i1 + "  "           # inside thead/tbody
        i3 = i2 + "  "           # inside tr

        # 4) Build pretty inner (thead + tbody)
        parts = []
        parts.append("\n")
        parts.append(f"{i1}<thead>\n")
        parts.append(f"{i2}<tr>\n")
        for h in HEADERS:
            parts.append(f"{i3}<th>{h}</th>\n")
        parts.append(f"{i2}</tr>\n")
        parts.append(f"{i1}</thead>\n")
        parts.append(f"{i1}<tbody>\n")
        for d, rev, desc, by in rows:
            parts.append(f"{i2}<tr>\n")
            parts.append(f"{i3}<td>{d}</td>\n")
            parts.append(f"{i3}<td>{rev}</td>\n")
            parts.append(f"{i3}<td>{desc}</td>\n")
            parts.append(f"{i3}<td>{by}</td>\n")
            parts.append(f"{i2}</tr>\n")
        parts.append(f"{i1}</tbody>\n")
        parts.append(f"{i0}")  # line up closing </table> with the open tag

        new_inner = "".join(parts)
        pretty_table = f"{open_tag}{new_inner}{close_tag}"

        # 5) Splice back
        return html[:m.start(1)] + pretty_table + html[m.end(3):]


    def _prettify_testing_table_in_html(self, html: str) -> str:
        """Rebuild the inner of <table class="testing-table"> with pretty, indented HTML."""
        rows = []
        for r in range(self.testing_table.rowCount()):
            def cell(c):
                it = self.testing_table.item(r, c)
                return it.text().strip() if it else ""
            rows.append((cell(0), cell(1), cell(2), cell(3), cell(4), cell(5), cell(6)))

        headers = ["Test No.", "Test Name", "Test Description", "Lower Limit", "Target Value", "Upper Limit", "Units"]
        return self._prettify_any_table_inner(
            html=html,
            table_class="testing-table",
            preferred_container_id="testing",
            headers=headers,
            rows=rows,
        )

    def _prettify_fmea_table_in_html(self, html: str) -> str:
        """Rebuild the inner of <table class="fmea-table"> with pretty, indented HTML."""
        rows = []
        for r in range(self.fmea_table.rowCount()):
            def cell(c):
                it = self.fmea_table.item(r, c)
                return it.text().strip() if it else ""
            rows.append((
                cell(0), cell(1), cell(2), cell(3), cell(4), cell(5), cell(6), cell(7),
                cell(8), cell(9), cell(10), cell(11), cell(12), cell(13), cell(14), cell(15), cell(16)
            ))

        headers = [
            "Item", "Potential Failure Mode", "Potential Effect of Failure", "Severity (1-10)",
            "Potential Cause(s)/Mechanism(s) of Failure", "Occurrence (1-10)", "Current Process Controls",
            "Detection (1-10)", "RPN", "Recommended Action(s)", "Responsibility", "Target Completion Date",
            "Actions Taken", "Resulting Severity", "Resulting Occurrence", "Resulting Detection", "New RPN"
        ]
        return self._prettify_any_table_inner(
            html=html,
            table_class="fmea-table",
            preferred_container_id="fmea",
            headers=headers,
            rows=rows,
        )

    def _prettify_any_table_inner(self, html: str, table_class: str, preferred_container_id: str,
                                headers: list[str], rows: list[tuple]) -> str:
        """
        Rebuilds the *inner* of a target <table class="..."> with pretty, indented HTML:
        <thead> with headers, <tbody> with rows.
        Preserves the exact opening <table ...> and closing </table> tags.
        Prefers a table inside <main>... or inside #preferred_container_id, otherwise first match anywhere.
        """
        # Find the target table segment in preferred locations
        def replace_first_tbody_in_segment(seg_html: str, seg_start_in_doc: int):
            # If the segment is a full <table ...>...</table>, m_tbl will capture open/inner/close
            m_tbl = re.search(rf'(?is)(<table\b[^>]*class="[^"]*\b{re.escape(table_class)}\b[^"]*"[^>]*>)(.*?)(</table>)', seg_html)
            if not m_tbl:
                return None
            open_tag, old_inner, close_tag = m_tbl.group(1), m_tbl.group(2), m_tbl.group(3)

            # Determine indentation based on where the table starts
            table_abs_start = seg_start_in_doc + m_tbl.start()
            line_start = html.rfind("\n", 0, table_abs_start) + 1
            base_indent = html[line_start:table_abs_start]
            # If the line is 'clean', use it; otherwise default to two spaces
            indent_tbl = base_indent if not base_indent.strip() else "  "

            i0 = indent_tbl          # aligns with <table> line column for </table>
            i1 = indent_tbl + "  "   # inside <table>
            i2 = i1 + "  "           # inside thead/tbody
            i3 = i2 + "  "           # inside tr

            # Build pretty inner
            parts = []
            parts.append("\n")
            parts.append(f"{i1}<thead>\n")
            parts.append(f"{i2}<tr>\n")
            for h in headers:
                parts.append(f"{i3}<th>{h}</th>\n")
            parts.append(f"{i2}</tr>\n")
            parts.append(f"{i1}</thead>\n")
            parts.append(f"{i1}<tbody>\n")
            for row in rows:
                parts.append(f"{i2}<tr>\n")
                for cell in row:
                    parts.append(f"{i3}<td>{cell}</td>\n")
                parts.append(f"{i2}</tr>\n")
            parts.append(f"{i1}</tbody>\n")
            parts.append(f"{i0}")  # position for </table> alignment

            new_inner = "".join(parts)
            pretty_table = f"{open_tag}{new_inner}{close_tag}"

            # Splice back this particular table (within seg_html), then splice seg_html back to html
            seg_new = seg_html[:m_tbl.start()] + pretty_table + seg_html[m_tbl.end():]
            return seg_new

        # Try <main> first
        m_main = re.search(r"(?is)(<main\b[^>]*>)(.*?)(</main>)", html)
        if m_main:
            main_inner = m_main.group(2)
            replaced = replace_first_tbody_in_segment(main_inner, m_main.start(2))
            if replaced is not None:
                return html[:m_main.start(2)] + replaced + html[m_main.end(2):]

        # Try preferred container div by id
        m_div = re.search(rf'(?is)(<div\b[^>]*id="{re.escape(preferred_container_id)}"[^>]*>)(.*?)(</div>)', html)
        if m_div:
            div_inner = m_div.group(2)
            replaced = replace_first_tbody_in_segment(div_inner, m_div.start(2))
            if replaced is not None:
                return html[:m_div.start(2)] + replaced + html[m_div.end(2):]

        # Fallback: first matching table anywhere
        replaced = replace_first_tbody_in_segment(html, 0)
        return replaced if replaced is not None else html

    def _force_pretty_table_segment(self, html: str, table_class: str) -> str:
        """
        As a last resort, pretty-print the FIRST <table class="...">…</table> segment by
        inserting newlines/indentation directly into the final HTML string. This runs
        after all other mutations so nothing can re-minify it.
        """
        m = re.search(rf'(?is)(<table\b[^>]*class="[^"]*\b{re.escape(table_class)}\b[^"]*"[^>]*>)(.*?)(</table>)', html)
        if not m:
            return html

        open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)
        table_abs_start = m.start(1)

        # Establish base indent from the original line
        line_start = html.rfind("\n", 0, table_abs_start) + 1
        base_indent = html[line_start:table_abs_start]
        indent_tbl = base_indent if not base_indent.strip() else "  "
        i0 = indent_tbl
        i1 = indent_tbl + "  "
        i2 = i1 + "  "
        i3 = i2 + "  "

        # Tokenize the inner with a very small HTML-ish lexer to insert line breaks
        # Keep <thead>, <tbody>, <tr>, <th>, <td> readable
        tokens = re.findall(r"(?is)<[^>]+>|[^<]+", inner)
        out = []
        depth = 0

        def emit(line, ind):
            out.append(ind + line + "\n")

        # Always rebuild header/body/rows cleanly if they exist
        # 1) Extract <thead>...</thead>
        m_thead = re.search(r"(?is)(<thead\b[^>]*>)(.*?)(</thead>)", inner)
        m_tbody = re.search(r"(?is)(<tbody\b[^>]*>)(.*?)(</tbody>)", inner)

        # If we have explicit thead/tbody, rebuild them structured; else, apply a generic pretty fallback
        if m_thead and m_tbody:
            # Headers
            headers_html = m_thead.group(2)
            hdrs = re.findall(r"(?is)<th\b[^>]*>(.*?)</th>", headers_html)
            # Rows
            body_html = m_tbody.group(2)
            rows = []
            for row_m in re.finditer(r"(?is)<tr\b[^>]*>(.*?)</tr>", body_html):
                cells = re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", row_m.group(1))
                rows.append(cells)

            # Rebuild inner cleanly
            rebuilt = []
            rebuilt.append("\n")
            rebuilt.append(f"{i1}<thead>\n")
            rebuilt.append(f"{i2}<tr>\n")
            for h in hdrs:
                rebuilt.append(f"{i3}<th>{h.strip()}</th>\n")
            rebuilt.append(f"{i2}</tr>\n")
            rebuilt.append(f"{i1}</thead>\n")
            rebuilt.append(f"{i1}<tbody>\n")
            for r in rows:
                rebuilt.append(f"{i2}<tr>\n")
                for c in r:
                    rebuilt.append(f"{i3}<td>{c.strip()}</td>\n")
                rebuilt.append(f"{i2}</tr>\n")
            rebuilt.append(f"{i1}</tbody>\n")
            rebuilt.append(f"{i0}")
            new_inner = "".join(rebuilt)
        else:
            # Fallback: split tags roughly and indent by tag type
            # (This path will still be much nicer than a single line.)
            new_inner_lines = []
            content = inner.strip()
            # Break between adjacent tags to insert basic newlines
            content = re.sub(r">\s*<", ">\n<", content)
            for line in content.splitlines():
                line = line.strip()
                low = line.lower()
                if low.startswith("</thead") or low.startswith("</tbody") or low.startswith("</tr"):
                    depth = max(0, depth - 1)
                indent = [i1, i2, i3, i3 + "  "][min(depth, 3)]
                new_inner_lines.append(indent + line)
                if low.startswith("<thead") or low.startswith("<tbody") or low.startswith("<tr"):
                    depth += 1
            new_inner = "\n" + "\n".join(new_inner_lines) + "\n" + i0

        pretty = f"{open_tag}{new_inner}{close_tag}"
        return html[:m.start(1)] + pretty + html[m.end(3):]

    def _open_downloads_dialog(self):
        pn = self.in_pn.text().strip()
        rev_default = self._downloads_state.get("rev") or self._latest_rev_from_ui()
        dlg = DownloadsDialog(pn, rev_default, initial=self._downloads_state, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            st = dlg.result_state()
            self._downloads_state.update({
                "datasheet": st["datasheet"],
                "ltspice":   st["ltspice"],
                "gerbers":   st["gerbers"],
                "cad":       st["cad"],
                "rev":       st["rev"],
            })
            items = self._downloads_items_from_state(pn, st["rev"], self._downloads_state)
            self.downloads_list.clear()
            for text, href in items:
                self.downloads_list.addItem(f"{text} | {href}")
            self._schedule_sync()

    def _latest_rev_from_ui(self) -> str:
        if self.rev_table.rowCount() == 0:
            return ""
        last = self.rev_table.rowCount() - 1
        it = self.rev_table.item(last, 1)
        return it.text().strip() if it else ""

    def _downloads_items_from_state(self, pn: str, rev: str, state: dict) -> list[tuple[str, str]]:
        items = []
        if state.get("datasheet") and pn:
            items.append(("Datasheet (PDF)", f"../datasheets/{pn}.pdf"))
        if state.get("ltspice") and pn:
            items.append(("LTspice File (.asc)", f"../ltspice/{pn}.asc"))
        if state.get("gerbers") and pn and rev:
            items.append(("Gerber Files (.zip)", f"../gerbers/{pn}-{rev}.zip"))
        if state.get("cad") and pn and rev:
            items.append(("EAGLE 6.3 Files", f"../cad/eagle-6-3/{pn}-{rev}.zip"))
        return items

    def _replace_downloads_ul(self, html: str, items: list[tuple[str, str]]) -> str:
        """
        Replace inner of first <ul class="download-list">…</ul> (prefer inside #downloads).
        Pretty, indented <li><a ...>Text</a></li> lines. Keeps outer <ul ...> and </ul>.
        """
        m_scope = re.search(r'(?is)(<div\b[^>]*id="downloads"[^>]*>)(.*?)(</div>)', html)
        search_region = html
        offset = 0
        if m_scope:
            search_region = m_scope.group(2)
            offset = m_scope.start(2)
        m_ul = re.search(r'(?is)(<ul\b[^>]*class="[^"]*\bdownload-list\b[^"]*"[^>]*>)(.*?)(</ul>)', search_region)
        if not m_ul:
            m_ul = re.search(r'(?is)(<ul\b[^>]*class="[^"]*\bdownload-list\b[^"]*"[^>]*>)(.*?)(</ul>)', html)
            if not m_ul:
                return html
            offset = 0

        open_tag, old_inner, close_tag = m_ul.group(1), m_ul.group(2), m_ul.group(3)
        ul_abs_start = offset + m_ul.start(1)
        line_start = html.rfind("\n", 0, ul_abs_start) + 1
        base_indent = html[line_start:ul_abs_start]
        indent_ul = base_indent if not base_indent.strip() else "  "
        i1 = indent_ul + "  "

        lines = ["\n"]
        for text, href in items:
            lines.append(f'{i1}<li><a href="{href}" rel="noopener noreferrer" target="_blank">{self._html_escape(text)}</a></li>\n')
        lines.append(indent_ul)
        new_inner = "".join(lines)
        pretty = f"{open_tag}{new_inner}{close_tag}"
        new_region = search_region[:m_ul.start(1)] + pretty + search_region[m_ul.end(3):]
        if m_scope:
            return html[:m_scope.start(2)] + new_region + html[m_scope.end(2):]
        return html[:m_ul.start(1)] + pretty + html[m_ul.end(3):]

    def _infer_rev_from_downloads(self, pn: str, downloads: list[tuple[str, str]]) -> str:
        """
        Try to infer REV from gerber/cad filenames like ../gerbers/PN-REV.zip or ../cad/eagle-6-3/PN-REV.zip.
        Returns "" if not found.
        """
        pn = (pn or "").strip()
        for _text, href in downloads:
            href = (href or "").strip()
            # Look for the basename without extension and try to split PN-REV
            m = re.search(r'/(?:gerbers|cad/eagle-6-3)/([^/\\]+)\.zip$', href, flags=re.IGNORECASE)
            if not m:
                continue
            base = m.group(1)  # e.g., "11A-001-A2"
            if pn and base.startswith(pn + "-"):
                return base[len(pn) + 1 :]  # after "PN-"
            # If PN is missing or doesn’t match exactly, try to find the last dash chunk as REV
            parts = base.split("-")
            if len(parts) >= 2:
                return parts[-1] if pn == "" else "-".join(parts[1:])
        return ""

    def _on_nav_context_menu(self, pos):
        idx = self.nav_list.indexAt(pos).row()
        menu = QMenu(self)

        act_ins_above = QAction("Insert Link Above", self, triggered=lambda: self._insert_nav_dialog(idx, rel=-1))
        act_ins_below = QAction("Insert Link Below", self, triggered=lambda: self._insert_nav_dialog(idx, rel=+1))
        menu.addAction(act_ins_above)
        menu.addAction(act_ins_below)

        if idx >= 0:
            act_edit = QAction("Edit…", self, triggered=lambda: self._edit_nav_dialog(idx))
            act_del  = QAction("Delete", self, triggered=self._nav_del)
            menu.addSeparator()
            menu.addAction(act_edit)
            menu.addAction(act_del)

        menu.exec_(self.nav_list.mapToGlobal(pos))

    def _insert_nav_dialog(self, anchor_row: int, rel: int):
        """
        Insert dialog relative to anchor_row.
        rel = -1 => above; +1 => below; if anchor_row < 0, insert at end.
        """
        # Pre-fill empty values
        dlg = NavLinkDialog("", "", parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        title, href = dlg.result()
        if not title:
            return

        # If user picked a file path, convert to relative href
        href = self._normalize_href(href)

        # Decide insertion row
        if anchor_row < 0:
            row = self.nav_list.count()
        else:
            row = max(0, anchor_row + (0 if rel < 0 else 1))

        self.nav_list.insertItem(row, f"{title} | {href or '#'}")
        self._schedule_sync()

    def _edit_nav_dialog(self, row: int):
        if row < 0 or row >= self.nav_list.count():
            return
        cur = self.nav_list.item(row).text()
        cur_title, cur_href = (cur.split(" | ", 1) + [""])[:2] if " | " in cur else (cur, "")
        dlg = NavLinkDialog(cur_title, cur_href, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        title, href = dlg.result()
        if not title:
            return
        href = self._normalize_href(href)
        self.nav_list.item(row).setText(f"{title} | {href or '#'}")
        self._schedule_sync()

    def _normalize_href(self, candidate: str) -> str:
        """
        If candidate is an absolute filesystem path, convert it to a site-relative href
        from the CURRENT HTML's directory; otherwise return as-is.
        Always use forward slashes.
        """
        if not candidate:
            return ""
        # If it already looks like a URL or relative web path, pass through
        if candidate.startswith(("http://", "https://", "/")):
            return candidate
        try:
            p = Path(candidate)
            if p.is_absolute():
                # compute relative to the current HTML directory
                if self.current_path:
                    start_dir = self.current_path.parent.resolve()
                    rel = os.path.relpath(str(p.resolve()), str(start_dir))
                    return rel.replace("\\", "/")
                return p.name.replace("\\", "/")
            # treat as relative filesystem path -> make it web-style slashes
            return candidate.replace("\\", "/")
        except Exception:
            return candidate.replace("\\", "/")

    def _replace_nav_ul(self, html: str, items: list[tuple[str, str]]) -> str:
        """
        Replace the inner of the first <ul class="nav-links">…</ul> with pretty, indented <li> rows.
        Keeps the existing <ul ...> opening tag and </ul> closing tag intact.
        Prefers a match inside <nav> (any depth), falls back to first match anywhere.
        """
        # Try to scope inside <nav> first
        m_scope = re.search(r'(?is)(<nav\b[^>]*>)(.*?)(</nav>)', html)
        search_region = html
        offset = 0
        if m_scope:
            search_region = m_scope.group(2)
            offset = m_scope.start(2)

        # Find the <ul class="nav-links">
        m_ul = re.search(r'(?is)(<ul\b[^>]*class="[^"]*\bnav-links\b[^"]*"[^>]*>)(.*?)(</ul>)', search_region)
        if not m_ul:
            # Fallback: anywhere in the document
            m_ul = re.search(r'(?is)(<ul\b[^>]*class="[^"]*\bnav-links\b[^"]*"[^>]*>)(.*?)(</ul>)', html)
            if not m_ul:
                return html
            offset = 0

        open_tag, old_inner, close_tag = m_ul.group(1), m_ul.group(2), m_ul.group(3)

        # Determine indentation from where the <ul> starts
        ul_abs_start = offset + m_ul.start(1)
        line_start = html.rfind("\n", 0, ul_abs_start) + 1
        base_indent = html[line_start:ul_abs_start]
        indent_ul = base_indent if not base_indent.strip() else "  "
        i1 = indent_ul + "  "  # indent for <li> lines

        # Build pretty inner
        lines = ["\n"]
        for text, href in items:
            safe_text = self._html_escape(text or "")
            safe_href = (href or "").replace("\\", "/")
            lines.append(f'{i1}<li><a href="{safe_href}">{safe_text}</a></li>\n')
        lines.append(indent_ul)
        new_inner = "".join(lines)

        pretty = f"{open_tag}{new_inner}{close_tag}"

        # Splice back into whichever region we used
        if m_scope and offset:
            new_region = search_region[:m_ul.start(1)] + pretty + search_region[m_ul.end(3):]
            return html[:m_scope.start(2)] + new_region + html[m_scope.end(2):]
        else:
            return html[:m_ul.start(1)] + pretty + html[m_ul.end(3):]

    def _replace_iframe_list(self, html: str, container_id: str, urls: list[str]) -> str:
        """
        Deterministically rebuild the ENTIRE <div id="{container_id}"> ... </div> block:
        - Preserve the original opening and closing tags
        - Replace the inner with <h2> + pretty video-wrapper blocks
        - Full-segment splice to avoid unbalanced </div> issues
        - Idempotent (no-ops if unchanged)
        """
        import re

        span = self._find_div_span_by_id(html, container_id)
        if not span:
            return html

        start_open, start_inner, end_inner, end_close = span
        open_tag = html[start_open:start_inner]
        close_tag = html[end_inner:end_close]
        inner_old = html[start_inner:end_inner]

        # Keep an existing H2 if present; else synthesize a sensible title
        m_h2 = re.search(r'(?is)<h2\b[^>]*>.*?</h2>', inner_old)
        if m_h2:
            h2_html = m_h2.group(0).strip()
        else:
            title = "Videos" if container_id == "videos" else (
                "Additional Resources" if container_id == "resources" else container_id.title()
            )
            h2_html = f"<h2>{title}</h2>"

        # Indentation based on the opening <div> line
        line_start = html.rfind("\n", 0, start_open) + 1
        base_indent = html[line_start:start_open]
        indent_div = base_indent if not base_indent.strip() else "  "
        i1 = indent_div + "  "

        # Normalize/keep only non-empty URLs
        urls = [ (u or "").strip() for u in urls if (u or "").strip() ]

        # Build new inner deterministically
        parts = []
        parts.append("\n")
        parts.append(i1 + h2_html + "\n")
        for u in urls:
            parts.append(
                f'{i1}<div class="video-wrapper">\n'
                f'{i1}  <iframe src="{u}" title="YouTube video player" width="560" height="315" loading="lazy" '
                f'referrerpolicy="strict-origin-when-cross-origin" '
                f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
                f'allowfullscreen frameborder="0"></iframe>\n'
                f"{i1}</div>\n"
            )
        parts.append(indent_div)
        inner_new = "".join(parts)

        # Idempotent compare (whitespace-insensitive)
        def _norm(s: str) -> str:
            s = re.sub(r">\s+<", "><", s.strip())
            s = re.sub(r"\s+", " ", s)
            return s

        if _norm(inner_new) == _norm(inner_old):
            return html  # nothing to change

        # FULL-SEGMENT REPLACE: open + new inner + close
        return html[:start_open] + open_tag + inner_new + close_tag + html[end_close:]

    def _on_url_list_context(self, lw: QListWidget, label: str, pos):
        idx = lw.indexAt(pos).row()
        m = QMenu(self)
        m.addAction(QAction("Add Above", self, triggered=lambda: self._insert_url_dialog(lw, idx, -1, label)))
        m.addAction(QAction("Add Below", self, triggered=lambda: self._insert_url_dialog(lw, idx, +1, label)))
        if idx >= 0:
            m.addSeparator()
            m.addAction(QAction("Edit…", self, triggered=lambda: self._edit_url_dialog(lw, idx, label)))
            m.addAction(QAction("Delete", self, triggered=lambda: (self._delete_selected_from_list(lw), self._schedule_sync())))
        m.exec_(lw.mapToGlobal(pos))

    def _insert_url_dialog(self, lw: QListWidget, anchor_row: int, rel: int, label: str):
        # Prefill nothing for new items
        dlg = SimpleUrlDialog("", "", parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        title, url = dlg.result()
        url = self._normalize_video_url(url) if label.lower().startswith("video") or label.lower().startswith("resource") else url
        text = f"{title} | {url}" if title else url
        # decide insertion row
        row = lw.count() if anchor_row < 0 else max(0, anchor_row + (0 if rel < 0 else 1))
        lw.insertItem(row, text)
        self._schedule_sync()

    def _edit_url_dialog(self, lw: QListWidget, row: int, label: str):
        if row < 0 or row >= lw.count():
            return
        cur = lw.item(row).text()
        # support both "Title | URL" and just "URL"
        if " | " in cur:
            cur_title, cur_url = (cur.split(" | ", 1) + [""])[:2]
        else:
            cur_title, cur_url = "", cur
        dlg = SimpleUrlDialog(cur_title, cur_url, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        title, url = dlg.result()
        url = self._normalize_video_url(url) if label.lower().startswith("video") or label.lower().startswith("resource") else url
        text = f"{title} | {url}" if title else url
        lw.item(row).setText(text)
        self._schedule_sync()

    def _delete_selected_from_list(self, lw: QListWidget):
        for it in lw.selectedItems():
            lw.takeItem(lw.row(it))

    def _normalize_video_url(self, url: str) -> str:
        """Convert common YouTube URLs to embed form; keep others as-is."""
        u = (url or "").strip()
        if not u:
            return u
        # Already embed
        if "youtube.com/embed/" in u:
            return u
        # youtu.be/<id>
        m = re.match(r"https?://(?:www\.)?youtu\.be/([A-Za-z0-9_\-]+)", u)
        if m:
            return f"https://www.youtube.com/embed/{m.group(1)}"
        # youtube.com/watch?v=<id>
        m = re.match(r"https?://(?:www\.)?youtube\.com/watch\?v=([A-Za-z0-9_\-]+)", u)
        if m:
            return f"https://www.youtube.com/embed/{m.group(1)}"
        # leave unchanged
        return u

    def _remove_orphan_video_wrappers(self, html: str) -> str:
        """
        Remove any <div class="video-wrapper">...</div> that lies OUTSIDE the
        #videos and #resources containers (depth-aware).
        """
        import re

        # Compute preserved inner ranges for videos/resources
        keep_ranges = []
        for cid in ("videos", "resources"):
            span = self._find_div_span_by_id(html, cid)
            if span:
                _, start_inner, end_inner, _ = span
                keep_ranges.append((start_inner, end_inner))

        def _inside_kept(i: int) -> bool:
            return any(a <= i < b for (a, b) in keep_ranges)

        # Find all wrappers in document
        wrappers = list(re.finditer(r'(?is)<div\b[^>]*class="[^"]*\bvideo-wrapper\b[^"]*"[^>]*>.*?</div>', html))
        if not wrappers:
            return html

        out = html
        removed = []
        for m in reversed(wrappers):
            if not _inside_kept(m.start()):
                out = out[:m.start()] + out[m.end():]
                removed.append((m.start(), m.end()))
        return out

    def _find_div_span_by_id(self, html: str, div_id: str):
        """
        Return (start_open, start_inner, end_inner, end_close) indices that bound
        the full <div id="div_id">...</div> region, with start_inner..end_inner being the inner.
        If not found, return None.
        """
        import re
        open_pat = re.compile(rf'(?is)<div\b[^>]*\bid\s*=\s*"{re.escape(div_id)}"[^>]*>')
        m = open_pat.search(html)
        if not m:
            return None
        start_open = m.start()
        pos = m.end()  # start scanning after the opening tag
        depth = 1
        # Simple tag scanner for <div ...> and </div>
        tag_pat = re.compile(r'(?is)</?\s*div\b[^>]*>')
        for mt in tag_pat.finditer(html, pos):
            tag = mt.group(0)
            if tag.lstrip().startswith("</"):
                depth -= 1
                if depth == 0:
                    # inner is from after the opening tag to mt.start()
                    return (start_open, m.end(), mt.start(), mt.end())
            else:
                depth += 1
        return None

    def _clear_layout_items(self, layout):
        while layout.count():
            it = layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def _add_image_or_placeholder(self, container_layout, file_path, missing_text: str):
        # Make the container layout edge-to-edge
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        view = ZoomPanImageView()
        view.set_image_path(file_path)  # or shows "IMAGE NOT FOUND"
        container_layout.addWidget(view, 1)  # <— stretch=1 so it fills the height

    def _resolve_rel(self, rel: str) -> Path:
        base = self.current_path.parent if self.current_path else Path(self.ctx.project_root)
        return (base / rel).resolve()

    def _refresh_schematic_and_layout_views(self, pn: str, schematic_srcs: list[str], layout_srcs: list[str]):
        # ----- Schematic -----
        self._clear_layout_items(self.schematic_container)

        schematic_paths: list[Path] = []
        for src in (schematic_srcs or []):
            src = (src or "").strip()
            if src:
                schematic_paths.append(self._resolve_rel(src))

        # Default PN_schematic_01..10 if none in HTML
        if not schematic_paths and pn:
            base = f"../images/{pn}_schematic_"
            found_any = False
            for i in range(1, 11):
                p = self._resolve_rel(f"{base}{i:02d}.png")
                if p.exists():
                    schematic_paths.append(p)
                    found_any = True
                elif found_any:
                    break

        if schematic_paths:
            for p in schematic_paths:
                self._add_image_or_placeholder(self.schematic_container, p, "IMAGE NOT FOUND")
        else:
            self._add_image_or_placeholder(self.schematic_container, self._resolve_rel("../images/PN_schematic_01.png"), "IMAGE NOT FOUND")

        self.schematic_container.addStretch(1)

        # ----- Layout -----
        self._clear_layout_items(self.layout_container)

        layout_paths: list[Path] = []
        for src in (layout_srcs or []):
            src = (src or "").strip()
            if src:
                layout_paths.append(self._resolve_rel(src))

        # Default PN_components_top.png if none in HTML
        if not layout_paths and pn:
            layout_paths.append(self._resolve_rel(f"../images/{pn}_components_top.png"))

        if layout_paths:
            for p in layout_paths:
                self._add_image_or_placeholder(self.layout_container, p, "IMAGE NOT FOUND")
        else:
            self._add_image_or_placeholder(self.layout_container, self._resolve_rel("../images/PN_components_top.png"), "IMAGE NOT FOUND")

        self.layout_container.addStretch(1)
    
    def _place_image_in_container(self, container_layout, img_path: str, missing_text: str):
        # Clear previous widgets
        while container_layout.count():
            it = container_layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        if not img_path:
            from PyQt5.QtWidgets import QLabel
            lbl = QLabel(missing_text)
            lbl.setAlignment(Qt.AlignCenter)
            container_layout.addWidget(lbl, 1)  # stretch=1 to fill space
            return

        view = ZoomPanImageView()
        view.set_image_path(img_path)
        container_layout.addWidget(view, 1)     # stretch=1 to fill space

    def _on_edit_ai_seeds(self):
        """Open the AI Seeds dialog, load current seeds from HTML, write back if accepted."""
        # Get current HTML from the editor
        getter = getattr(self, "get_editor_text", None)
        html = getter() if callable(getter) else ""
        if not html.strip():
            QMessageBox.information(self, "Edit AI Seeds", "Open an HTML file first.")
            return

        # Read (and normalize legacy) seeds from the page
        seeds = parse_ai_seeds_from_html(html)

        # Show dialog
        dlg = AISeedsDialog(self, seeds)
        if dlg.exec_() != QDialog.Accepted:
            return

        # Write back pretty, single-key structure: description_seed/testing_seed/fmea_seed
        new_seeds = dlg.result_seeds()
        new_html = write_ai_seeds_into_html(html, new_seeds)

        if new_html and new_html != html:
            # Push into editor so autosave/dirty flow continues as usual
            self._set_editor_text(new_html)
            self.status.showMessage("AI seeds updated.", 3000)

    def _read_ai_seeds_from_html(self, html: str) -> dict:
        """
        Read seeds from <script id='ai-seeds-json' type='application/json'>.
        Returns FLATTENED keys: description_seed, testing_seed, fmea_seed.
        Backward compatible with legacy {"testing":{"dtp_seed","atp_seed"}}.
        """
        default = {"description_seed": "", "testing_seed": "", "fmea_seed": ""}

        def _parse_payload(s: str) -> dict:
            try:
                data = json.loads(s)
            except Exception:
                return default.copy()

            out = default.copy()
            out["description_seed"] = (data.get("description_seed") or "").strip()
            out["fmea_seed"] = (data.get("fmea_seed") or "").strip()
            # Prefer flattened testing_seed; else merge legacy dtp/atp
            ts = (data.get("testing_seed") or "").strip()
            if not ts:
                t = data.get("testing", {}) if isinstance(data.get("testing"), dict) else {}
                parts = [(t.get("dtp_seed") or "").strip(), (t.get("atp_seed") or "").strip()]
                ts = "\n".join([p for p in parts if p])
            out["testing_seed"] = ts
            return out

        # BeautifulSoup path
        if BeautifulSoup:
            try:
                soup = BeautifulSoup(html, "html.parser")
                node = soup.select_one('script#ai-seeds-json[type="application/json"]')
                if node and node.string:
                    return _parse_payload(node.string)
            except Exception:
                pass

        # Regex fallback
        m = re.search(r'(?is)<script[^>]+id=["\']ai-seeds-json["\'][^>]*>(.*?)</script>', html)
        if m:
            return _parse_payload(m.group(1))

        return default.copy()

    def _write_ai_seeds_to_html(self, html: str, seeds: dict) -> str:
        """
        Upsert the seeds block with FLATTENED keys only:
        { "description_seed": "...", "testing_seed": "...", "fmea_seed": "..." }
        """
        payload = json.dumps({
            "description_seed": (seeds.get("description_seed") or "").strip(),
            "testing_seed": (seeds.get("testing_seed") or "").strip(),
            "fmea_seed": (seeds.get("fmea_seed") or "").strip(),
        }, ensure_ascii=False)

        if BeautifulSoup:
            try:
                soup = BeautifulSoup(html, "html.parser")
                main = soup.find("main")
                seeds_div = soup.select_one("#ai-seeds")
                if seeds_div is None:
                    seeds_div = soup.new_tag(
                        "div",
                        id="ai-seeds",
                        **{"class": "tab-content", "data-hidden": "true", "aria-hidden": "true"}
                    )
                    if main is not None:
                        main.append(seeds_div)
                    elif soup.body:
                        soup.body.append(seeds_div)

                script = seeds_div.select_one('script#ai-seeds-json[type="application/json"]')
                if script is None:
                    script = soup.new_tag("script", id="ai-seeds-json", type="application/json")
                    seeds_div.append(script)

                script.string = payload
                return str(soup)
            except Exception:
                pass

        # Regex fallback: replace or insert
        pat = r'(?is)(<script[^>]+id=["\']ai-seeds-json["\'][^>]*>)(.*?)(</script>)'
        if re.search(pat, html):
            return re.sub(pat, rf'\1{payload}\3', html, count=1)

        block = (
            '\n<div id="ai-seeds" class="tab-content" data-hidden="true" aria-hidden="true">\n'
            f'  <script id="ai-seeds-json" type="application/json">{payload}</script>\n'
            '</div>\n'
        )
        if re.search(r'(?is)</main>', html):
            return re.sub(r'(?is)</main>', block + r'</main>', html, count=1)
        return re.sub(r'(?is)</body>', block + r'</body>', html, count=1)

    def _replace_description_html(self, html: str, body_text: str) -> str:
        """
        Replace the inner of <div id="description"> with:
        <h2>Description</h2>
        <p>...</p>
        <p>...</p>
        Pretty-indented; preserves the existing <div ...> open/close tags.
        If body_text is empty, keep only the <h2>.
        """
        import re

        m = re.search(r'(?is)(<div\b[^>]*id="description"[^>]*>)(.*?)(</div>)', html)
        if not m:
            return html  # no #description container present

        open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)

        # Indentation based on where the <div ... id="description"> starts
        div_abs_start = m.start(1)
        line_start = html.rfind("\n", 0, div_abs_start) + 1
        base_indent = html[line_start:div_abs_start]
        indent_div = base_indent if not base_indent.strip() else "  "
        i1 = indent_div + "  "  # inside div
        # i2 reserved if you want deeper indent per <p>, but we keep one level

        def _esc(s: str) -> str:
            return (
                (s or "")
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

        # Build pretty inner
        parts = []
        parts.append("\n")
        parts.append(f"{i1}<h2>Description</h2>\n")

        txt = (body_text or "").strip()
        if txt:
            # Split into paragraphs on blank lines; within a para, single newlines become <br/>
            paras = re.split(r"\n\s*\n", txt)
            for para in paras:
                para = para.strip()
                if not para:
                    continue
                lines = [_esc(l) for l in para.split("\n")]
                joined = "<br/>".join(lines)
                parts.append(f"{i1}<p>{joined}</p>\n")

        parts.append(indent_div)
        new_inner = "".join(parts)
        pretty_div = f"{open_tag}{new_inner}{close_tag}"

        return html[:m.start(1)] + pretty_div + html[m.end(3):]

    def _prettify_description_div(self, html: str) -> str:
        """
        Rebuild the inner of <div id="description"> with clean newlines/indentation.
        Preserves the <div ...> and </div> tags and keeps existing <h2> and <p> content.
        """
        import re

        m = re.search(r'(?is)(<div\b[^>]*id="description"[^>]*>)(.*?)(</div>)', html)
        if not m:
            return html

        open_div, inner, close_div = m.group(1), m.group(2), m.group(3)

        # Determine indentation based on where the <div> starts
        div_abs_start = m.start(1)
        line_start = html.rfind("\n", 0, div_abs_start) + 1
        base_indent = html[line_start:div_abs_start]
        indent_div = base_indent if not base_indent.strip() else "  "
        i1 = indent_div + "  "

        # Extract existing <h2> (optional) and all <p> blocks (as-is)
        h2_match = re.search(r'(?is)<h2\b[^>]*>.*?</h2>', inner)
        p_blocks = re.findall(r'(?is)<p\b[^>]*>.*?</p>', inner)

        # If nothing to pretty, bail out
        if not h2_match and not p_blocks:
            return html

        lines = ["\n"]
        # Keep existing heading or default to "Description"
        if h2_match:
            lines.append(i1 + h2_match.group(0).strip() + "\n")
        else:
            lines.append(i1 + "<h2>Description</h2>\n")

        # Append each paragraph on its own indented line
        for p in p_blocks:
            lines.append(i1 + p.strip() + "\n")

        lines.append(indent_div)
        pretty_inner = "".join(lines)
        return html[:m.start(1)] + open_div + pretty_inner + close_div + html[m.end(3):]

    def _on_edit_ai_seeds(self):
        """Open the AI Seeds dialog, load current seeds from HTML, write back if accepted."""
        getter = self.get_editor_text if callable(self.get_editor_text) else None
        html = getter() if getter else ""
        if not html.strip():
            QMessageBox.information(self, "Edit AI Seeds", "Open an HTML file first.")
            return

        seeds = self._read_ai_seeds_from_html(html)
        dlg = AiSeedsDialog(self, seeds)
        if dlg.exec_() != QDialog.Accepted:
            return

        new_seeds = dlg.result_seeds()  # flattened keys
        new_html = self._write_ai_seeds_to_html(html, new_seeds)
        if new_html and new_html != html:
            self._set_editor_text(new_html)

    def _on_forms_current_changed(self, idx: int):
        # Persist main tab focus
        if idx >= 0:
            self._last_main_tab_index = idx
        # Also capture sub-tab if current is the Metadata tab
        w = self.forms.widget(idx)
        if hasattr(self, "meta_tab") and w is self.meta_tab:
            self._last_meta_sub_index = self.meta_tab.currentIndex() if self.meta_tab.count() else 0

    def _on_meta_current_changed(self, idx: int):
        # Persist sub-tab focus
        if idx >= 0:
            self._last_meta_sub_index = idx

    def _restore_focus_after_build(self):
        # Restore main tab
        if 0 <= self._last_main_tab_index < self.forms.count():
            self.forms.setCurrentIndex(self._last_main_tab_index)
        # Restore sub-tab (if current main is metadata)
        if hasattr(self, "meta_tab") and self.forms.currentWidget() is self.meta_tab:
            if 0 <= self._last_meta_sub_index < self.meta_tab.count():
                # avoid signal feedback loops
                blocker = QSignalBlocker(self.meta_tab)
                try:
                    self.meta_tab.setCurrentIndex(self._last_meta_sub_index)
                finally:
                    del blocker

    def _on_toggle_optional(self, name: str, checked: bool):
        if getattr(self, "_is_updating_optionals", False):
            return
        self._opt_visibility[name] = checked
        updated = self._apply_optional_visibility(None)  # uses self._current_html
        self._set_html_to_view(updated)
        self._refresh_optionals_summary()

    # --- keep exactly one of these ---
    def load_html_into_form(self, html_text: str):
        """Load the current file's HTML into the form (board or collection)."""
        # --- DIAG START: load_html_into_form ---
        try:
            import os, sys, re
            print("\n[DIAG load] called:",
                "len(html)=", len(html_text) if html_text else 0,
                "path=", getattr(self, "current_path", None))
            # if you set current_type earlier, show it; otherwise compute a guess
            print("[DIAG load] current_type(before) =", getattr(self, "current_type", None))
            print("[DIAG load] details?=", bool(re.search(r'id="details"', html_text or "", re.I)),
                "description?=", bool(re.search(r'id="description"', html_text or "", re.I)))
            sys.stdout.flush()
        except Exception as _e:
            print("[DIAG load] print failed:", _e)
        # --- DIAG END: load_html_into_form ---

        self._current_html = html_text
        self._update_view_bar_for_path(getattr(self, "current_path", None))

        if getattr(self, "current_type", "other") == "board":
            with self._suppress_updates():
                # --- DIAG START: load -> populate call ---
                try:
                    has_board_tab = hasattr(self, "board_tab")
                    has_layout = bool(hasattr(getattr(self, "board_tab", None), "layout") and self.board_tab.layout() is not None)
                    print("[DIAG load] about to populate:",
                        "has board_tab:", has_board_tab,
                        "has layout:", has_layout)
                    # Ensure the form exists without changing behavior
                    if hasattr(self, "_ensure_board_form"):
                        self._ensure_board_form()
                        print("[DIAG load] _ensure_board_form() done.")
                    import sys; sys.stdout.flush()
                except Exception as _e:
                    print("[DIAG load] pre-populate failed:", _e)
                # --- DIAG END: load -> populate call ---
                self._populate_board_from_html(html_text)
                self._set_optional_checkboxes_from_html(html_text)  # reflect once
            applied = self._apply_optional_visibility(html_text)     # rebuild sections/buttons
            self._set_html_to_view(applied)
        else:
            self._set_html_to_view(html_text)

    def _refresh_optionals_summary(self):
        # Uses the top-bar state: self._opt_visibility and/or self._opt_checks
        for name, lbl in getattr(self, "_opt_status_labels", {}).items():
            visible = self._opt_visibility.get(name, True)
            lbl.setText(f"{name}: {'Visible' if visible else 'Hidden'}")

    def _on_forms_current_changed(self, idx: int):
        """Remember the main tab index; also remember Metadata sub-tab if applicable."""
        if idx >= 0:
            self._last_main_tab_index = idx
        if hasattr(self, "meta_tab") and self.forms.widget(idx) is self.meta_tab:
            self._last_meta_sub_index = self.meta_tab.currentIndex() if self.meta_tab.count() else 0

    def _on_meta_current_changed(self, idx: int):
        """Call this from _build_board_forms after creating self.meta_tab."""
        if idx >= 0:
            self._last_meta_sub_index = idx

    def _restore_focus_after_build(self):
        """Call at end of load_html_file after building/populating forms."""
        if 0 <= self._last_main_tab_index < self.forms.count():
            self.forms.setCurrentIndex(self._last_main_tab_index)
        if hasattr(self, "meta_tab") and self.forms.currentWidget() is self.meta_tab:
            if 0 <= self._last_meta_sub_index < self.meta_tab.count():
                blocker = QSignalBlocker(self.meta_tab)
                try:
                    self.meta_tab.setCurrentIndex(self._last_meta_sub_index)
                finally:
                    del blocker

    # --- unify toggle handler ---
    def _on_toggle_optional(self, name: str, checked: bool):
        """Show/hide the named optional tab and rewrite HTML once."""
        if getattr(self, "_is_updating_optionals", False):
            return
        # ensure containers exist
        if not hasattr(self, "_opt_visibility"):
            self._opt_visibility = {}
        self._opt_visibility[name] = bool(checked)

        updated = self._apply_optional_visibility(None)  # uses self._current_html
        self._set_html_to_view(updated)
        if hasattr(self, "_refresh_optionals_summary"):
            self._refresh_optionals_summary()

    # --- the only _apply_optional_visibility you keep ---
    def _apply_optional_visibility(self, html: str | None = None) -> str:
        """
        Rebuild the <div class="tabs"> buttons and add/remove matching section <div id="...">
        blocks according to the Optional Tabs checkboxes.

        Details, Schematic, and Revisions are always present.
        Safe to call with no argument: will use self._current_html.
        Does nothing on collection pages.
        """
        import re

        # Use current buffer if not provided
        if html is None:
            html = self._current_html or ""
        if not html:
            return html

        # Skip optional processing on non-board pages
        if getattr(self, "current_type", "other") != "board":
            return html

        flags = self._optional_flags()

        LABELS = {
            "details":     "Details",
            "schematic":   "Schematic",
            "description": "Description",
            "layout":      "Layout",
            "downloads":   "Downloads",
            "resources":   "Additional Resources",
            "videos":      "Videos",
            "fmea":        "FMEA",
            "testing":     "Testing",
            "revisions":   "Revision History",
        }
        mandatory_ids = ["details", "schematic", "revisions"]
        optional_ids  = ["description", "layout", "downloads", "resources", "videos", "fmea", "testing"]

        enabled_optional = [tid for tid in optional_ids if flags.get(tid, False)]
        target_ids = [mandatory_ids[0], mandatory_ids[1], *enabled_optional, mandatory_ids[2]]

        # ---- 1) Ensure/create the <div class="tabs"> ... </div> ----
        m_tabs = re.search(r'(?is)(<div\b[^>]*class="[^"]*\btabs\b[^"]*"[^>]*>)(.*?)(</div>)', html)
        if not m_tabs:
            tab_block = (
                '<div class="tab-container">\n'
                '  <div class="tabs" aria-label="Sections" role="tablist">\n'
                '  </div>\n'
                '</div>\n'
            )
            if re.search(r'(?is)</main>', html):
                html = re.sub(r'(?is)</main>', tab_block + r'</main>', html, count=1)
            else:
                html = re.sub(r'(?is)</body>', tab_block + r'</body>', html, count=1)
            m_tabs = re.search(r'(?is)(<div\b[^>]*class="[^"]*\btabs\b[^"]*"[^>]*>)(.*?)(</div>)', html)
            if not m_tabs:
                return html

        open_tabs, inner_tabs, close_tabs = m_tabs.group(1), m_tabs.group(2), m_tabs.group(3)

        # Determine current active tab
        m_active = re.search(
            r'(?is)<button[^>]*\bclass="[^"]*\btab\b[^"]*\bactive\b[^"]*"[^>]*\baria-controls="([^"]+)"',
            inner_tabs
        )
        active_id = m_active.group(1).strip() if m_active else None
        if active_id not in target_ids:
            active_id = target_ids[0]

        # Rebuild pretty one-button-per-line block
        btn_lines = ["\n"]
        for tid in target_ids:
            is_active = (tid == active_id)
            active_cls = " active" if is_active else ""
            btn_lines.append(f'  <button class="tab{active_cls}" role="tab" aria-controls="{tid}">{LABELS[tid]}</button>\n')

        pretty_tabs = f"{open_tabs}{''.join(btn_lines)}{close_tabs}"
        html = html[:m_tabs.start(1)] + pretty_tabs + html[m_tabs.end(3):]

        # ---- 2) Ensure presence/absence of matching section <div id="..."> blocks ----
        def ensure_section(h: str, sec_id: str) -> str:
            if not re.search(rf'(?is)<div\b[^>]*id="{re.escape(sec_id)}"[^>]*>', h):
                # append a minimal section near </main>
                sec_html = (
                    f'<div id="{sec_id}" class="tab-content">\n'
                    f'  <h2>{LABELS[sec_id]}</h2>\n'
                    f'</div>\n'
                )
                if re.search(r'(?is)</main>', h):
                    return re.sub(r'(?is)</main>', sec_html + r'</main>', h, count=1)
                return re.sub(r'(?is)</body>', sec_html + r'</body>', h, count=1)
            return h

        def remove_section(h: str, sec_id: str) -> str:
            pat = re.compile(rf'(?is)<div\b[^>]*id="{re.escape(sec_id)}"[^>]*>.*?</div>\s*')
            return re.sub(pat, "", h)

        for must in mandatory_ids:
            if not re.search(rf'(?is)<div\b[^>]*id="{re.escape(must)}"[^>]*>', html):
                html = ensure_section(html, must)

        for tid in optional_ids:
            if tid in enabled_optional:
                html = ensure_section(html, tid)
            else:
                if re.search(rf'(?is)<div\b[^>]*id="{re.escape(tid)}"[^>]*>', html):
                    html = remove_section(html, tid)

        # persist and return
        self._current_html = html
        return html

    def _rewrite_tab_buttons_in_html(self, html: str, visibility: dict[str, bool]) -> str:
        """
        Rebuilds the inner of: <div class="tab-container"><div class="tabs" role="tablist"> ... </div></div>
        according to 'visibility' dict keyed by section ids:
        details, schematic, description, videos, layout, downloads, resources, fmea, testing, revisions.

        Preserves <div class="tab-container"> and <div class="tabs ..."> opening tags.
        Ensures one 'active' button remains (prefers first visible in the canonical order).
        Produces pretty, one-button-per-line markup.
        """
        import re
        # Canonical order + labels
        ORDER = [
            "details", "schematic",
            "description", "videos", "layout", "downloads", "resources",
            "fmea", "testing",
            "revisions",
        ]
        LABELS = {
            "details": "Details",
            "schematic": "Schematic",
            "description": "Description",
            "videos": "Videos",
            "layout": "Layout",
            "downloads": "Downloads",
            "resources": "Additional Resources",
            "fmea": "FMEA",
            "testing": "Testing",
            "revisions": "Revision History",
        }

        # Which are visible now?
        visible_ids = [sec for sec in ORDER if visibility.get(sec, False)]

        if not visible_ids:
            # Safety: never wipe tablist completely—fall back to essential
            visible_ids = ["details", "schematic", "revisions"]

        # Determine currently active (so we can try to preserve it)
        active_id = None
        m_active = re.search(
            r'(?is)<button[^>]*\bclass="[^"]*\btab\b[^"]*\bactive\b[^"]*"[^>]*\baria-controls="([^"]+)"',
            html
        )
        if m_active:
            active_id = m_active.group(1).strip()

        # If current active is not visible anymore, pick first visible
        if active_id not in visible_ids:
            active_id = visible_ids[0]

        # Build pretty buttons markup (two-space indent under <div class="tabs">)
        def build_buttons(active: str) -> str:
            lines = []
            for sec_id in visible_ids:
                label = LABELS.get(sec_id, sec_id.title())
                is_active = (sec_id == active)
                cls = 'class="tab active"' if is_active else 'class="tab"'
                aria_sel = ' aria-selected="true"' if is_active else ""
                lines.append(f'  <button aria-controls="{sec_id}"{aria_sel} {cls} data-tab="{sec_id}" role="tab" type="button">{label}</button>')
            # Join with newlines and trailing newline for cleanliness
            return "\n" + "\n".join(lines) + "\n"

        # Soup path first (cleaner + safer)
        try:
            if BeautifulSoup:
                soup = BeautifulSoup(html, "html.parser")
                tc = soup.select_one('div.tab-container')
                tabs = tc.select_one('div.tabs') if tc else None
                if not tabs:
                    # Try a global .tabs as a fallback
                    tabs = soup.select_one('div.tabs')
                if not tabs:
                    return html  # no tablist; don't change

                # Remember indentation at <div class="tabs">
                tabs_str = str(tabs)
                # Replace its children with our buttons (as HTML)
                # We rebuild the tabs element entirely to avoid stray text nodes
                new_tabs = BeautifulSoup(str(tabs), "html.parser")
                new_tabs_div = new_tabs.select_one('div.tabs')
                if not new_tabs_div:
                    return html
                # clear children
                for ch in list(new_tabs_div.children):
                    ch.extract()
                # inject our buttons as raw HTML
                buttons_html = build_buttons(active_id)
                inject = BeautifulSoup(buttons_html, "html.parser")
                new_tabs_div.append(inject)

                # Replace old tabs with new tabs
                tabs.replace_with(new_tabs_div)

                # Pretty print buttons block: indent under tabs line
                out = str(soup)

                # Optional tidy: ensure each <button> sits on its own line in the final text
                out = re.sub(
                    r'(?is)(<div[^>]*\bclass="[^"]*\btabs\b[^"]*"[^>]*>)\s*.*?(</div>)',
                    lambda m: m.group(1) + buttons_html + m.group(2),
                    out,
                    count=1
                )
                return out
        except Exception:
            pass

        # Regex fallback: replace the inner of the first <div class="tabs" ...> ... </div>
        m = re.search(r'(?is)(<div\b[^>]*class="[^"]*\btabs\b[^"]*"[^>]*>)(.*?)(</div>)', html)
        if not m:
            return html

        open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)

        # Find indentation before the buttons block for pretty alignment
        tabs_abs = m.start(1)
        line_start = html.rfind("\n", 0, tabs_abs) + 1
        base_indent = html[line_start:tabs_abs]
        indent = base_indent if not base_indent.strip() else "  "
        # Build with extra indent (we already add 2 spaces per button in build_buttons)
        new_inner = build_buttons(active_id)
        pretty_block = f"{open_tag}{new_inner}{close_tag}"
        return html[:m.start(1)] + pretty_block + html[m.end(3):]

    def _optional_flags(self) -> dict:
        """
        Returns the enabled/disabled state for optional tabs.
        Reads from the TOP-BAR checkboxes (self._opt_checks / _opt_visibility).
        Keys must be the canonical IDs used in _apply_optional_visibility().
        """
        # canonical ids in the system
        ids = ["description", "layout", "downloads", "resources", "videos", "fmea", "testing"]

        flags = {}
        # Prefer live widgets if present
        for tid in ids:
            cb = None
            # self._opt_checks may be keyed by id ("description") or label ("Description").
            # Try id first; then try Title Case.
            if hasattr(self, "_opt_checks"):
                cb = self._opt_checks.get(tid) or self._opt_checks.get(tid.title())
            if cb is not None:
                flags[tid] = bool(cb.isChecked())
                continue

            # fallback to cached visibility map (set by toggle / load)
            if hasattr(self, "_opt_visibility"):
                if tid in self._opt_visibility:
                    flags[tid] = bool(self._opt_visibility[tid])
                    continue

            # default (safe) if nothing available
            flags[tid] = False

        return flags

    def _apply_optional_visibility(self, html: str | None = None) -> str:
        """
        Rebuild the <div class="tabs"> buttons and add/remove matching section <div id="...">
        blocks according to the Optional Tabs checkboxes.
        Details, Schematic, and Revisions are always present.

        Safe to call with no argument: will use self._current_html.
        Does nothing on collection pages.
        """
        import re

        # Use current buffer if not provided
        if html is None:
            html = self._current_html or ""
        if not html:
            return html

        # Skip optional processing on non-board pages
        if getattr(self, "current_type", "other") != "board":
            return html

        flags = self._optional_flags()

        # Canonical labels and order
        LABELS = {
            "details":     "Details",
            "schematic":   "Schematic",
            "description": "Description",
            "layout":      "Layout",
            "downloads":   "Downloads",
            "resources":   "Additional Resources",
            "videos":      "Videos",
            "fmea":        "FMEA",
            "testing":     "Testing",
            "revisions":   "Revision History",
        }
        mandatory_ids = ["details", "schematic", "revisions"]
        optional_ids  = ["description", "layout", "downloads", "resources", "videos", "fmea", "testing"]

        # Which optional tabs should be present
        enabled_optional = [tid for tid in optional_ids if flags.get(tid, False)]

        # Final button order
        target_ids = [mandatory_ids[0], mandatory_ids[1], *enabled_optional, mandatory_ids[2]]

        # ---- 1) Find/create the <div class="tabs"> ... </div> ----
        m_tabs = re.search(r'(?is)(<div\b[^>]*class="[^"]*\btabs\b[^"]*"[^>]*>)(.*?)(</div>)', html)
        if not m_tabs:
            # Create a minimal tab-container + tabs under <main>, else before </body>
            tab_block = (
                '<div class="tab-container">\n'
                '  <div class="tabs" aria-label="Sections" role="tablist">\n'
                '  </div>\n'
                '</div>\n'
            )
            if re.search(r'(?is)</main>', html):
                html = re.sub(r'(?is)</main>', tab_block + r'</main>', html, count=1)
            else:
                html = re.sub(r'(?is)</body>', tab_block + r'</body>', html, count=1)
            m_tabs = re.search(r'(?is)(<div\b[^>]*class="[^"]*\btabs\b[^"]*"[^>]*>)(.*?)(</div>)', html)
            if not m_tabs:
                # If we still couldn't find it, bail safely
                return html

        # ---- 2) Determine current active tab (to preserve if still present) ----
        active_id = "schematic"
        tabs_inner = m_tabs.group(2)
        m_active = re.search(r'(?is)<button\b[^>]*\bclass="[^"]*\bactive\b[^"]*"[^>]*\bdata-tab="([^"]+)"', tabs_inner)
        if not m_active:
            m_active = re.search(r'(?is)<button\b[^>]*\baria-selected="true"[^>]*\bdata-tab="([^"]+)"', tabs_inner)
        if m_active:
            cand = m_active.group(1).strip()
            if cand in target_ids:
                active_id = cand

        # ---- 3) Build pretty buttons HTML (preserve indentation) ----
        tabs_open_abs_start = m_tabs.start(1)
        line_start = html.rfind("\n", 0, tabs_open_abs_start) + 1
        base_indent = html[line_start:tabs_open_abs_start]
        indent0 = base_indent if not base_indent.strip() else "  "
        indent1 = indent0 + "  "

        def mk_btn(tab_id: str) -> str:
            label = LABELS.get(tab_id, tab_id.title())
            selected = (tab_id == active_id)
            attrs = (
                f'aria-controls="{tab_id}" '
                f'class="tab{" active" if selected else ""}" '
                f'data-tab="{tab_id}" role="tab" type="button"'
            )
            if selected:
                attrs = attrs.replace('class="tab', 'aria-selected="true" class="tab', 1)
            return f'{indent1}<button {attrs}>{label}</button>\n'

        buttons_html = indent0 + "\n" + "".join(mk_btn(tid) for tid in target_ids) + indent0

        # Splice new buttons into the tabs div (replace only the inner content)
        new_tabs_block = m_tabs.group(1) + buttons_html + m_tabs.group(3)
        html = html[:m_tabs.start()] + new_tabs_block + html[m_tabs.end():]

        # ---- 4) Ensure enabled sections exist; remove disabled ones ----
        def ensure_section(h: str, sec_id: str) -> str:
            if re.search(rf'(?is)<div\b[^>]*id="{re.escape(sec_id)}"[^>]*>', h):
                return h  # already exists
            label = LABELS.get(sec_id, sec_id.title())
            block = (
                f'<div class="tab-content" id="{sec_id}">\n'
                f'  <h2>{label}</h2>\n'
                f'</div>\n'
            )
            if re.search(r'(?is)</main>', h):
                return re.sub(r'(?is)</main>', block + r'</main>', h, count=1)
            return re.sub(r'(?is)</body>', block + r'</body>', h, count=1)

        def remove_section(h: str, sec_id: str) -> str:
            pat = re.compile(rf'(?is)<div\b[^>]*id="{re.escape(sec_id)}"[^>]*>.*?</div>\s*')
            return re.sub(pat, "", h)

        # Always-on sections must exist
        for must in mandatory_ids:
            if not re.search(rf'(?is)<div\b[^>]*id="{re.escape(must)}"[^>]*>', html):
                html = ensure_section(html, must)

        # Optional sections on/off
        for tid in optional_ids:
            if tid in enabled_optional:
                if not re.search(rf'(?is)<div\b[^>]*id="{re.escape(tid)}"[^>]*>', html):
                    html = ensure_section(html, tid)
            else:
                if re.search(rf'(?is)<div\b[^>]*id="{re.escape(tid)}"[^>]*>', html):
                    html = remove_section(html, tid)

        # persist and return
        self._current_html = html
        return html

    def _wire_optional_checkboxes(self):
        """Connect optional-tab checkboxes to schedule an HTML rebuild."""
        for cb in (
            self.opt_description,
            self.opt_layout,
            self.opt_downloads,
            self.opt_resources,
            self.opt_videos,
            self.opt_fmea,
            self.opt_testing,
        ):
            cb.stateChanged.connect(self._schedule_sync)

    # --- canonical optional flags from the live checkboxes/top bar ---
    def _optional_flags(self) -> dict:
        """
        Return the desired visibility for optional sections based on checkboxes,
        falling back to cached _opt_visibility when necessary.
        """
        flags = {}

        # Prefer the live top-bar checkboxes if you maintain them there
        for tid, cb in getattr(self, "_opt_checks", {}).items():
            flags[tid.lower()] = bool(cb.isChecked())

        # Fallback to cached map for anything missing
        if hasattr(self, "_opt_visibility"):
            for k, v in self._opt_visibility.items():
                lk = k.lower()
                if lk not in flags:
                    flags[lk] = bool(v)

        # Default safe values for known optionals (off unless present)
        for k in ("description", "videos", "layout", "downloads", "resources", "fmea", "testing"):
            flags.setdefault(k, False)

        return flags

    # --- single source of truth for reflecting checkboxes from HTML ---
    def _set_optional_checkboxes_from_html(self, html_text: str) -> None:
        """
        Reflect existing visibility from HTML into the already-built checkboxes.
        (No rebuilding here, so no duplicates.)
        """
        import re
        self._is_updating_optionals = True
        try:
            for name, cb in getattr(self, "_opt_checks", {}).items():
                # presence/absence check — tailor this to your actual markers/sections
                has_section = re.search(rf'(?is)<div\b[^>]*id="{re.escape(name.lower())}"[^>]*>', html_text) is not None
                want_checked = bool(has_section)
                if cb.isChecked() != want_checked:
                    cb.blockSignals(True)
                    cb.setChecked(want_checked)
                    cb.blockSignals(False)
                if not hasattr(self, "_opt_visibility"):
                    self._opt_visibility = {}
                self._opt_visibility[name] = want_checked
        finally:
            self._is_updating_optionals = False

    def _rebuild_view_bar_from_names(self, names: list[str]):
        """
        Only call this if the actual set/order of optional sections changes.
        Clears the row and reconnects each checkbox exactly once.
        """
        from functools import partial
        self._clear_layout_items(self._view_bar_layout)   # ← your helper
        self._opt_checks.clear()

        for name in names:
            cb = QCheckBox(name, self._view_bar)
            cb.setChecked(self._opt_visibility.get(name, True))

            try:
                cb.toggled.disconnect()
            except Exception:
                pass
            cb.toggled.connect(partial(self._on_toggle_optional, name))

            self._view_bar_layout.addWidget(cb)
            self._opt_checks[name] = cb

        self._view_bar_layout.addStretch(1)

    def _set_optional_checkboxes_from_html(self, html_text: str):
        """
        Reflect existing visibility from HTML into the already-built checkboxes.
        (No rebuilding here, so no duplicates.)
        """
        import re
        self._is_updating_optionals = True
        try:
            for name, cb in self._opt_checks.items():
                hidden = re.search(
                    rf'OPTIONAL:start\s+name="{re.escape(name)}"[^>]*-->.*?<div[^>]*data-optional-wrap="{re.escape(name)}"',
                    html_text, re.DOTALL
                ) is not None
                want_checked = not hidden
                if cb.isChecked() != want_checked:
                    cb.blockSignals(True)
                    cb.setChecked(want_checked)
                    cb.blockSignals(False)
                self._opt_visibility[name] = want_checked
        finally:
            self._is_updating_optionals = False

    def _is_collection_filename(self, path: Path) -> bool:
        """
        Your rule: files named XX.html or XXX.html are collection pages.
        """
        if not path or not str(path).lower().endswith(".html"):
            return False
        stem = Path(path).stem
        return len(stem) in (2, 3)

    def _update_view_bar_for_path(self, path: Path | None):
        is_board = bool(path) and not self._is_collection_filename(path)
        self.current_type = "board" if is_board else "collection"
        # show/hide the top bar
        self._view_bar.setVisible(is_board)
        # (optional) also disable so it can't get keyboard focus when hidden
        self._view_bar.setEnabled(is_board)

    def _show_no_file_placeholder(self):
        self._clear_forms()
        placeholder = QWidget()
        v = QVBoxLayout(placeholder)
        lbl = QLabel("No file loaded. Select a collection or board HTML page.")
        lbl.setAlignment(Qt.AlignCenter)
        v.addWidget(lbl)
        self.forms.addTab(placeholder, "Forms")

        # hide the top checkbox bar in no-file state
        self.current_path = None
        self.current_type = "other"
        self._update_view_bar_for_path(None)

    def on_tree_selection(self, index):
        path = self._path_from_index(index)
        if not path or not path.exists() or not str(path).lower().endswith(".html"):
            with self._suppress_updates():
                self.current_path = None
                self.current_type = "other"
                self._update_view_bar_for_path(None)
                self._show_no_file_placeholder()  # whatever you use
            return

        self.current_path = path
        self._update_view_bar_for_path(path)

        html = Path(path).read_text(encoding="utf-8", errors="ignore")
        self.load_html_into_form(html)

    def _set_html_to_view(self, html: str, *, update_editor: bool = True, update_preview: bool = True) -> None:
        """
        Central place to push the latest HTML into the UI.
        - Saves to self._current_html
        - Updates a text editor widget if present
        - Updates a preview (QWebEngineView) if present
        """
        self._current_html = html

        # 1) Update the raw editor (best-effort: uses whatever you have)
        if update_editor:
            editor = None
            for attr in ("html_editor", "editor", "editor_text", "txt_editor"):
                if hasattr(self, attr):
                    editor = getattr(self, attr)
                    break

            if callable(getattr(self, "set_editor_text", None)):
                # If you have an explicit setter, use it
                try:
                    self.set_editor_text(html)
                except Exception:
                    pass
            elif editor is not None:
                try:
                    # Prefer plain text for HTML source editors
                    if hasattr(editor, "blockSignals"):
                        editor.blockSignals(True)
                    if hasattr(editor, "setPlainText"):
                        editor.setPlainText(html)
                    elif hasattr(editor, "setHtml"):
                        editor.setHtml(html)
                finally:
                    if hasattr(editor, "blockSignals"):
                        editor.blockSignals(False)

        # 2) Update a live preview if you keep one around
        if update_preview:
            preview = None
            for attr in ("webview", "preview", "html_preview", "pdf_view"):  # pdf_view ignored
                if hasattr(self, attr):
                    preview = getattr(self, attr)
                    break
            # Only update QWebEngineView-like objects
            if preview is not None and hasattr(preview, "setHtml"):
                try:
                    preview.setHtml(html)
                except Exception:
                    pass

    def _populate_board_from_html(self, html: str) -> None:
        """
        Parse board fields from HTML and populate the form widgets.
        """
        self._d("[DIAG] populate called:", bool(html), "len(html)=", len(html) if html else 0)
        if not html:
            self._d("[DIAG] empty HTML; abort populate.")
            return

        # Ensure form exists (no-op if already built)
        if hasattr(self, "_ensure_board_form"):
            try:
                self._ensure_board_form()
                self._d("[DIAG] _ensure_board_form done.")
            except Exception as _e:
                self._d("[DIAG] _ensure_board_form error:", repr(_e))

        # --- parse ---
        import re
        try:
            from bs4 import BeautifulSoup
        except Exception as _e:
            self._d("[DIAG] BeautifulSoup import failed:", repr(_e))
            return

        soup = BeautifulSoup(html or "", "html.parser")

        def norm(s: str | None) -> str:
            return re.sub(r"\s+", " ", (s or "").strip())

        def meta(*names):
            for name in names:
                tag = soup.find("meta", attrs={"name": re.compile(rf"^{re.escape(name)}$", re.I)})
                if tag and tag.has_attr("content"):
                    v = norm(tag.get("content"))
                    if v:
                        return v
            return ""

        pn_val          = meta("pn", "part-number", "partnumber")
        title_val       = meta("board-title", "title", "name")
        board_size_val  = meta("board-size", "board_dimensions", "board-dimensions")
        pieces_val      = meta("pieces-per-panel", "pieces", "per-panel")
        panel_size_val  = meta("panel-size", "panel_dimensions", "panel-dimensions")
        slogan_val      = meta("slogan", "tagline")
        keywords_val    = meta("keywords")
        descr_meta_val  = meta("description")  # SEO/summary

        def dl_lookup(label):
            dt = soup.find("dt", string=re.compile(rf"^\s*{re.escape(label)}\s*$", re.I))
            if dt:
                dd = dt.find_next_sibling("dd")
                if dd:
                    return norm(dd.get_text())
            return ""

        pn_val         = pn_val         or dl_lookup("PN")
        title_val      = title_val      or dl_lookup("Title")
        board_size_val = board_size_val or dl_lookup("Board Size")
        pieces_val     = pieces_val     or dl_lookup("Pieces per Panel")
        panel_size_val = panel_size_val or dl_lookup("Panel Size")
        slogan_val     = slogan_val     or dl_lookup("Slogan")
        keywords_val   = keywords_val   or dl_lookup("Keywords")

        def table_lookup(*labels):
            for tbl in soup.find_all("table"):
                for tr in tbl.find_all("tr"):
                    cells = tr.find_all(["th", "td"])
                    if len(cells) >= 2:
                        key = norm(cells[0].get_text())
                        val = norm(cells[1].get_text())
                        for L in labels:
                            if re.fullmatch(rf"{re.escape(L)}", key, re.I) and val:
                                return val
            return ""

        pn_val         = pn_val         or table_lookup("PN", "Part Number")
        title_val      = title_val      or table_lookup("Title", "Board Title", "Name")
        board_size_val = board_size_val or table_lookup("Board Size", "Board Dimensions")
        pieces_val     = pieces_val     or table_lookup("Pieces per Panel", "Pieces/Panel", "Per Panel")
        panel_size_val = panel_size_val or table_lookup("Panel Size", "Panel Dimensions")
        slogan_val     = slogan_val     or table_lookup("Slogan", "Tagline")
        keywords_val   = keywords_val   or table_lookup("Keywords")

        # fallbacks
        if not title_val:
            ttag = soup.find("title")
            if ttag:
                title_val = norm(ttag.get_text())
        if not pn_val and title_val:
            m = re.match(r'\s*([A-Za-z0-9][A-Za-z0-9\-\._]*)\s*\|', title_val)
            if m:
                pn_val = m.group(1)
        if not title_val:
            h1 = soup.find("h1")
            if h1:
                title_val = norm(h1.get_text())

        desc_body_val = ""
        desc_div = soup.find(id="description") or soup.find("section", id="description")
        if desc_div:
            desc_body_val = norm(desc_div.get_text())
        if not desc_body_val:
            any_desc = soup.find(class_=re.compile(r"\bdescription\b", re.I))
            if any_desc:
                desc_body_val = norm(any_desc.get_text())
        if not desc_body_val:
            desc_body_val = descr_meta_val

        self._d("[DIAG] parsed",
                "PN=", repr(pn_val),
                "Title=", repr(title_val),
                "SEOdesc.len=", len(descr_meta_val or ""),
                "Bodydesc.len=", len(desc_body_val or ""),
                "BoardSize=", repr(board_size_val),
                "Pieces=", repr(pieces_val),
                "PanelSize=", repr(panel_size_val),
                "Keywords.len=", len(keywords_val or ""))

        # --- write to widgets ---
        aliases = {
            "in_title":        ("in_title", "meta_title", "title_edit"),
            "in_description":  ("in_description", "meta_description", "description_edit"),
            "in_keywords":     ("in_keywords", "meta_keywords", "keywords_edit"),
            "in_pn":           ("in_pn", "board_pn", "pn_edit"),
            "in_board_size":   ("in_board_size", "board_size_edit"),
            "in_pieces":       ("in_pieces", "panel_pieces", "pieces_edit"),
            "in_panel_size":   ("in_panel_size", "panel_size_edit"),
            "in_slogan":       ("in_slogan", "slogan_edit"),
            "txt_description": ("txt_description", "description_body", "description_text"),
        }

        def _get_widget(*names):
            for n in names:
                if hasattr(self, n):
                    return getattr(self, n)
            return None

        def _set_line(widget, txt):
            if widget is None:
                return
            try:
                widget.blockSignals(True)
            except Exception:
                pass
            try:
                if hasattr(widget, "setText"):
                    widget.setText(txt or "")
                elif hasattr(widget, "setPlainText"):
                    widget.setPlainText(txt or "")
            finally:
                try:
                    widget.blockSignals(False)
                except Exception:
                    pass

        _set_line(_get_widget(*aliases["in_title"]),       title_val)
        _set_line(_get_widget(*aliases["in_description"]), descr_meta_val)   # SEO/short
        _set_line(_get_widget(*aliases["in_keywords"]),    keywords_val)
        _set_line(_get_widget(*aliases["in_pn"]),          pn_val)
        _set_line(_get_widget(*aliases["in_board_size"]),  board_size_val)
        _set_line(_get_widget(*aliases["in_pieces"]),      pieces_val)
        _set_line(_get_widget(*aliases["in_panel_size"]),  panel_size_val)
        _set_line(_get_widget(*aliases["in_slogan"]),      slogan_val)

        body_widget = _get_widget(*aliases["txt_description"])
        if body_widget is not None:
            try:
                body_widget.blockSignals(True)
            except Exception:
                pass
            try:
                if hasattr(body_widget, "setPlainText"):
                    body_widget.setPlainText(desc_body_val or "")
                elif hasattr(body_widget, "setText"):
                    body_widget.setText(desc_body_val or "")
            finally:
                try:
                    body_widget.blockSignals(False)
                except Exception:
                    pass

        self._d("[DIAG] board form populated")

    @contextmanager
    def _suppress_updates(self):
        prev = getattr(self, "_suppress_form_signals", False)
        self._suppress_form_signals = True
        try:
            yield
        finally:
            self._suppress_form_signals = prev

    def _schedule_sync(self):
        # don't sync while we're populating from HTML
        if getattr(self, "_suppress_form_signals", False):
            return
        self._debounce.start()

    def _sync_forms_to_editor(self):
        if getattr(self, "_suppress_form_signals", False):
            return
        # ... your existing sync-to-HTML code ...

    def init_debug_window(self) -> None:
        """
        Create (or find) a major 'Debug Window' tab and wire a lightweight logger.
        Call once after your UI/tabwidget is built (e.g., at the end of __init__).
        """
        # Find a tab widget to host the major tab (first QTabWidget under this widget)
        tabw = None
        if hasattr(self, "tabs") and isinstance(getattr(self, "tabs"), QTabWidget):
            tabw = self.tabs
        else:
            tabw = self.findChild(QTabWidget)
        if tabw is None:
            # Fallback: create a tab widget at root if none exists
            tabw = QTabWidget(self)
            lay = self.layout()
            if lay is None:
                lay = QVBoxLayout(self)
                self.setLayout(lay)
            lay.addWidget(tabw)

        # If already created, return
        if getattr(self, "_debug_tab_idx", None) is not None and hasattr(self, "debug_text"):
            return

        # Build the Debug tab
        dbg_page = QWidget()
        dbg_layout = QVBoxLayout(dbg_page)
        dbg_text = QTextEdit(dbg_page)
        dbg_text.setReadOnly(True)
        # Monospace, gentle word wrap off for logs
        dbg_text.setLineWrapMode(QTextEdit.NoWrap)
        dbg_text.setPlaceholderText("Debug output will appear here…")
        dbg_layout.addWidget(dbg_text)

        idx = tabw.addTab(dbg_page, "Debug Window")
        self._debug_tab_idx = idx
        self.debug_text = dbg_text
        self._debug_tabw = tabw

        # optional: jump cursor to end on text changes
        def _auto_scroll():
            cursor = self.debug_text.textCursor()
            cursor.movePosition(cursor.End)
            self.debug_text.setTextCursor(cursor)
        self.debug_text.textChanged.connect(_auto_scroll)

    def clear_debug_window(self) -> None:
        if hasattr(self, "debug_text"):
            self.debug_text.clear()

    def _d(self, *parts) -> None:
        """
        Append a timestamped log line to the Debug Window (if available),
        else print to stdout. Safe to call from anywhere.
        """
        msg = " ".join(str(p) for p in parts)
        ts = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss.zzz")
        line = f"[{ts}] {msg}"

        # If we have a debug window, append there (ensure on GUI thread)
        if hasattr(self, "debug_text") and self.debug_text is not None:
            def _append():
                # Keep logs lightweight: limit to last ~5000 lines
                self.debug_text.append(line)
                # optional soft cap
                max_blocks = 5000
                doc = self.debug_text.document()
                if doc.blockCount() > max_blocks:
                    # remove oldest excess blocks
                    cur = doc.findBlockByNumber(0).position()
                    end = doc.findBlockByNumber(doc.blockCount() - max_blocks).position()
                    cursor = self.debug_text.textCursor()
                    cursor.setPosition(cur)
                    cursor.setPosition(end, cursor.KeepAnchor)
                    cursor.removeSelectedText()
                    cursor.deletePreviousChar()
            QTimer.singleShot(0, _append)
        else:
            print(line)

    # ===================== DEBUG WINDOW (major tab) =====================
    def _init_debug_window(self) -> None:
        """
        Ensure a 'Debug Window' major tab exists on self.forms.
        Safe to call any time; buffers lines until ready.
        The tab will appear alongside 'Forms' and 'Raw Text'.
        """
        # prepare buffer
        if not hasattr(self, "_dbg_buffer"):
            self._dbg_buffer = []

        # forms not ready yet? try again on next tick
        if not hasattr(self, "forms") or not isinstance(self.forms, QTabWidget):
            QTimer.singleShot(0, self._init_debug_window)
            return

        # already installed?
        if getattr(self, "_dbg_tab_ready", False) and getattr(self, "debug_text", None):
            return

        # If a tab titled "Debug Window" already exists, reuse it
        for i in range(self.forms.count()):
            if self.forms.tabText(i).strip().lower() == "debug window":
                page = self.forms.widget(i)
                self.debug_text = page.findChild(QTextEdit) or QTextEdit(page)
                self._debug_tab_idx = i
                self._dbg_tab_ready = True
                self._flush_debug_buffer()
                return

        # Build the page
        page = QWidget(self.forms)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        self.debug_text = QTextEdit(page)
        self.debug_text.setReadOnly(True)
        self.debug_text.setLineWrapMode(QTextEdit.NoWrap)
        self.debug_text.setPlaceholderText("Debug output will appear here…")
        layout.addWidget(self.debug_text)

        # Add as a new major tab
        self._debug_tab_idx = self.forms.addTab(page, "Debug Window")
        self._dbg_tab_ready = True

        # Auto-scroll to bottom on new text
        def _auto_scroll():
            cur = self.debug_text.textCursor()
            cur.movePosition(cur.End)
            self.debug_text.setTextCursor(cur)
        self.debug_text.textChanged.connect(_auto_scroll)

        # Flush anything logged before the tab existed
        self._flush_debug_buffer()

    def _flush_debug_buffer(self) -> None:
        """Push any buffered lines into the Debug Window if it's ready."""
        if not getattr(self, "_dbg_tab_ready", False) or not getattr(self, "debug_text", None):
            return
        for line in getattr(self, "_dbg_buffer", []):
            try:
                self.debug_text.append(line)
            except Exception:
                pass
        self._dbg_buffer.clear()

    def debug(self, msg: str) -> None:
        """Append a timestamped line to the Debug Window (buffers until ready)."""
        try:
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            line = f"[{ts}] {msg}"
        except Exception:
            line = str(msg)

        if getattr(self, "_dbg_tab_ready", False) and getattr(self, "debug_text", None):
            try:
                self.debug_text.append(line)
            except Exception:
                # if append fails, fall back to buffer
                self._dbg_buffer.append(line)
        else:
            if not hasattr(self, "_dbg_buffer"):
                self._dbg_buffer = []
            self._dbg_buffer.append(line)

    # Optional: tiny timer context
    from contextlib import contextmanager
    from time import perf_counter

    @contextmanager
    def _dbg_time(self, label: str):
        t0 = perf_counter()
        self.debug(f"{label}: start")
        try:
            yield
        finally:
            self.debug(f"{label}: {(perf_counter() - t0) * 1000:.1f} ms")

    # =================== /DEBUG WINDOW (major tab) =====================
