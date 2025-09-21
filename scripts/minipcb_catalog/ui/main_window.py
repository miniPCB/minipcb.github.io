from __future__ import annotations

from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any, Callable
import re
import json
import datetime

from PyQt5.QtCore import Qt, QDir, QTimer, QPoint
from PyQt5.QtGui import QCloseEvent, QPixmap
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QTreeView, QFileSystemModel, QFileDialog,
    QTabWidget, QPlainTextEdit, QTextEdit, QLineEdit, QLabel,
    QPushButton, QFormLayout, QHBoxLayout, QVBoxLayout, QAction, QMessageBox,
    QStatusBar, QInputDialog, QMenu, QFileIconProvider, QStyle, QApplication,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QDialog,
    QDialogButtonBox, QCheckBox, QListWidget, QListWidgetItem, QComboBox,
    QGridLayout, QSizePolicy
)

from ..app import AppContext
from .. import constants
from ..services.file_service import FileService, WriteOptions
from ..services.html_service import HTMLService
from ..services.image_service import ImageService
from ..services.index_service import IndexService
from ..services.template_service import TemplateService


# ---------- Plain Qt icons (no overlays)
class _PlainIconProvider(QFileIconProvider):
    def icon(self, info):
        try:
            from PyQt5.QtCore import QFileInfo
            if isinstance(info, QFileInfo):
                if info.isDir():
                    return QApplication.style().standardIcon(QStyle.SP_DirIcon)
                return QApplication.style().standardIcon(QStyle.SP_FileIcon)
        except Exception:
            pass
        return QApplication.style().standardIcon(QStyle.SP_FileIcon)


# ---------- Helpers
def _now_stamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _rel_href(from_file: Path, site_root: Path, target_rel_to_root: Path) -> str:
    try:
        base = (site_root / from_file.relative_to(site_root).parent)
        rel = Path.relpath((site_root / target_rel_to_root), base)
        return str(rel).replace("\\", "/")
    except Exception:
        return target_rel_to_root.as_posix()


class _FitImageLabel(QLabel):
    """Keep original pixmap; scale-to-fit on resize (no crop)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._orig: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(320)
        self.setText("")

    def set_image_path(self, path: str):
        self._orig = None
        self.clear()
        if not path:
            self.setText("No image")
            return
        pix = QPixmap(path)
        if pix.isNull():
            self.setText(f"Image not found:\n{path}")
            return
        self._orig = pix
        self._rescale()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rescale()

    def _rescale(self):
        if self._orig is None:
            return
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        self.setPixmap(self._orig.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))


# ========================= Main Window =========================
class MainWindow(QMainWindow):
    """
    Tabs: Metadata | Sections | Navigation | Review | Stats
    Sections: Details | Description | Videos | Schematic | Layout | Downloads | Additional Resources | FMEA | Testing
    Seed-edit buttons live only in the top toolbar (always available).
    """

    _SECTION_IDS = (
        "details", "description", "videos", "schematic", "layout",
        "downloads", "resources", "fmea", "testing"
    )

    _DIV_BY_ID_RX_FMT = r'<div[^>]+id=["\']{id}["\'][^>]*>(?P<body>.*?)</div>'
    _IMG_SRC_RX = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
    _IMG_ALT_RX = re.compile(r'alt=["\']([^"\']*)["\']', re.IGNORECASE)
    _IFRAME_SRC_RX = re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
    _SEEDS_SCRIPT_RX = re.compile(
        r'(<script[^>]+id=["\']ai-seeds-json["\'][^>]*>)(.*?)(</script>)',
        re.IGNORECASE | re.DOTALL
    )
    _NAV_UL_RX = re.compile(r'(<ul[^>]*class=["\']nav-links["\'][^>]*>)(?P<body>.*?)(</ul>)',
                            re.IGNORECASE | re.DOTALL)

    def __init__(self, ctx: AppContext, autosave_seconds: int = constants.DEFAULT_AUTOSAVE_SECONDS):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(constants.APP_NAME)
        self.resize(1400, 900)

        # Services
        self.files = FileService(ctx)
        self.html = HTMLService()
        self.images = ImageService(ctx)
        self.index = IndexService(ctx)
        self.templates = TemplateService(ctx)

        # State
        self.current_path: Optional[Path] = None
        self.current_html: str = ""
        self.current_is_markdown: bool = False
        self.dirty: bool = False
        self.autosave_seconds = max(5, int(autosave_seconds))
        self._countdown = self.autosave_seconds
        self._last_context_index = None

        # UI
        self._build_menu()
        self._build_body()
        self._build_status()

        # Autosave timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick_autosave)
        self.timer.start(1000)

        # Bus hookups
        self.ctx.bus.status.connect(self._set_status)
        self._set_status("Ready")
        self._update_file_count_status()
        self._update_autosave_label()

    # ---------- Menu
    def _build_menu(self):
        mb = self.menuBar()
        m_file = mb.addMenu("&File")

        m_new = m_file.addMenu("New")
        act_new_board = QAction("Board Page…", self)
        act_new_coll = QAction("Collection Page…", self)
        act_new_board.triggered.connect(lambda: self._new_file_dialog(kind="board", target_dir=None))
        act_new_coll.triggered.connect(lambda: self._new_file_dialog(kind="collection", target_dir=None))
        m_new.addAction(act_new_board)
        m_new.addAction(act_new_coll)

        act_open = QAction("Open…", self)
        act_open.triggered.connect(self._open_dialog)
        m_file.addAction(act_open)

        self.act_save = QAction("Save", self)
        self.act_save.setShortcut("Ctrl+S")
        self.act_save.triggered.connect(self.save_current_page)
        m_file.addAction(self.act_save)

        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_tools = mb.addMenu("&Tools")
        act_clean = QAction("Clean / Prettify HTML", self)
        act_clean.triggered.connect(self._update_html_formatting)
        m_tools.addAction(act_clean)

    # ---------- Body
    def _build_body(self):
        splitter = QSplitter(); splitter.setOrientation(Qt.Horizontal)

        # Left: file explorer
        self.fs_model = QFileSystemModel(self)
        self.fs_model.setIconProvider(_PlainIconProvider())
        self.fs_model.setRootPath(str(self.ctx.root))
        self.fs_model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.fs_model.setNameFilters(["*.html", "*.htm", "*.md", "*.markdown"])
        self.fs_model.setNameFilterDisables(False)

        self.explorer = QTreeView()
        self.explorer.setModel(self.fs_model)
        self.explorer.setRootIndex(self.fs_model.index(str(self.ctx.root)))
        self.explorer.setSortingEnabled(True)
        self.explorer.doubleClicked.connect(self._open_from_index)
        self.explorer.setColumnWidth(0, 340)
        self.explorer.setColumnHidden(1, True)
        self.explorer.setColumnHidden(2, True)
        self.explorer.setContextMenuPolicy(Qt.CustomContextMenu)
        self.explorer.customContextMenuRequested.connect(self._on_tree_context)
        splitter.addWidget(self.explorer)

        # Right: top row + tabs
        right = QWidget(); rv = QVBoxLayout(right); rv.setContentsMargins(6, 6, 6, 6); rv.setSpacing(8)

        # Top toolbar: path + seeds + generate + clean + autosave
        top_row = QHBoxLayout()
        self.lbl_path = QLabel("")

        # Edit seeds (always available)
        self.btn_seed_desc = QPushButton("Edit Description Seed…")
        self.btn_seed_desc.clicked.connect(self._open_desc_seed_dialog)
        self.btn_seed_fmea = QPushButton("Edit FMEA Seed…")
        self.btn_seed_fmea.clicked.connect(self._open_fmea_seed_dialog_single)
        self.btn_seed_testing = QPushButton("Edit Testing Seeds…")
        self.btn_seed_testing.clicked.connect(self._open_testing_seeds_dialog)

        # Generate content buttons + ETA labels
        self.btn_gen_desc = QPushButton("Generate Description")
        self.btn_gen_desc.clicked.connect(self._gen_description)
        self.lbl_desc_ai = QLabel("AI: idle")

        self.btn_gen_fmea = QPushButton("Generate FMEA")
        self.btn_gen_fmea.clicked.connect(self._gen_fmea)
        self.lbl_fmea_ai = QLabel("AI: idle")

        self.btn_gen_dtp = QPushButton("Generate DTP")
        self.btn_gen_dtp.clicked.connect(self._gen_dtp)
        self.lbl_dtp_ai = QLabel("AI: idle")

        self.btn_gen_atp = QPushButton("Generate ATP")
        self.btn_gen_atp.clicked.connect(self._gen_atp)
        self.lbl_atp_ai = QLabel("AI: idle")

        self.btn_update_html = QPushButton("Update HTML")
        self.btn_update_html.setToolTip("Clean/prettify the HTML source without touching the current form fields.")
        self.btn_update_html.clicked.connect(self._update_html_formatting)

        self.lbl_autosave = QLabel("Saved")

        top_row.addWidget(self.lbl_path)
        top_row.addStretch(1)
        # seeds
        top_row.addWidget(self.btn_seed_desc)
        top_row.addWidget(self.btn_seed_fmea)
        top_row.addWidget(self.btn_seed_testing)
        top_row.addSpacing(12)
        # generate
        top_row.addWidget(self.btn_gen_desc); top_row.addWidget(self.lbl_desc_ai)
        top_row.addWidget(self.btn_gen_fmea); top_row.addWidget(self.lbl_fmea_ai)
        top_row.addWidget(self.btn_gen_dtp); top_row.addWidget(self.lbl_dtp_ai)
        top_row.addWidget(self.btn_gen_atp); top_row.addWidget(self.lbl_atp_ai)
        top_row.addSpacing(12)
        top_row.addWidget(self.btn_update_html)
        top_row.addSpacing(12)
        top_row.addWidget(self.lbl_autosave)
        rv.addLayout(top_row)

        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True)
        rv.addWidget(self.tabs, 1)

        # --------- Metadata tab
        self.tab_meta = QWidget(); form = QFormLayout(self.tab_meta); form.setVerticalSpacing(8)
        self.meta_title = QLineEdit()
        self.meta_keywords = QTextEdit(); self.meta_keywords.setAcceptRichText(False); self.meta_keywords.setMinimumHeight(60)
        self.meta_desc = QTextEdit(); self.meta_desc.setAcceptRichText(False); self.meta_desc.setMinimumHeight(90)
        self.meta_h1 = QLineEdit()
        self.meta_slogan = QLineEdit()
        form.addRow("Title:", self.meta_title)
        form.addRow("Meta Keywords:", self.meta_keywords)
        form.addRow("Meta Description:", self.meta_desc)
        form.addRow("H1:", self.meta_h1)
        form.addRow("Slogan:", self.meta_slogan)
        for w in (self.meta_title, self.meta_h1, self.meta_slogan):
            w.textChanged.connect(lambda *_: self._on_dirty(True))
        for w in (self.meta_keywords, self.meta_desc):
            w.textChanged.connect(lambda *_: self._on_dirty(True))
        self.tabs.addTab(self.tab_meta, "Metadata")

        # --------- Sections tab
        self.tab_sections = QWidget(); sv = QVBoxLayout(self.tab_sections); sv.setContentsMargins(0,0,0,0); sv.setSpacing(8)

        comp_box = QGroupBox("Page Components")
        comp_row = QHBoxLayout(comp_box); comp_row.setSpacing(12)
        self.chk_desc = QCheckBox("Description")
        self.chk_videos = QCheckBox("Videos")
        self.chk_downloads = QCheckBox("Downloads")
        self.chk_resources = QCheckBox("Additional Resources")
        self.chk_fmea = QCheckBox("FMEA")
        self.chk_testing = QCheckBox("Testing")
        for c in (self.chk_desc, self.chk_videos, self.chk_downloads, self.chk_resources, self.chk_fmea, self.chk_testing):
            c.setChecked(True); comp_row.addWidget(c); c.toggled.connect(self._on_components_changed)
        comp_row.addStretch(1)
        sv.addWidget(comp_box)

        self.subtabs = QTabWidget(self.tab_sections)
        self.subtabs.currentChanged.connect(self._on_subtab_changed)

        # ----- Details
        self.w_details = QWidget(); detf = QFormLayout(self.w_details)
        self.det_part = QLineEdit()
        self.det_title = QLineEdit()
        self.det_board = QLineEdit()
        self.det_pieces = QLineEdit()
        self.det_panel = QLineEdit()
        for ed in (self.det_part, self.det_title, self.det_board, self.det_pieces, self.det_panel):
            ed.textChanged.connect(lambda *_: self._on_dirty(True))
        self.det_part.textChanged.connect(self._on_part_changed)
        detf.addRow("Part No:", self.det_part)
        detf.addRow("Title:", self.det_title)
        detf.addRow("Board Size:", self.det_board)
        detf.addRow("Pieces per Panel:", self.det_pieces)
        detf.addRow("Panel Size:", self.det_panel)
        self.subtabs.addTab(self.w_details, "Details")

        # ----- Description
        self.w_desc = QWidget(); vdesc = QVBoxLayout(self.w_desc)
        self.txt_desc_generated = QTextEdit(); self.txt_desc_generated.setAcceptRichText(True); self.txt_desc_generated.setMinimumHeight(150)
        self.txt_desc_generated.textChanged.connect(lambda: self._on_dirty(True))
        vdesc.addWidget(self.txt_desc_generated, 1)
        # Hidden seed
        self._seed_desc = QTextEdit(); self._seed_desc.setAcceptRichText(False); self._seed_desc.setVisible(False)
        self._seed_desc.textChanged.connect(lambda: self._on_dirty(True))
        vdesc.addWidget(self._seed_desc)
        self.subtabs.addTab(self.w_desc, "Description")

        # ----- Videos
        self.tbl_videos = self._make_table(["Video URL"])
        self.subtabs.addTab(self._wrap_table_with_buttons(self.tbl_videos, tag="videos"), "Videos")

        # ----- Schematic
        self.w_schematic = QWidget(); schf = QFormLayout(self.w_schematic)
        self.sch_src = QLineEdit(); self.sch_alt = QLineEdit()
        self.sch_src.setPlaceholderText("../images/<PN>_schematic_01.png"); self.sch_alt.setPlaceholderText("Schematic")
        self.sch_src.textChanged.connect(lambda *_: (self._on_dirty(True), self._maybe_refresh_image_preview("Schematic")))
        self.sch_alt.textChanged.connect(lambda *_: self._on_dirty(True))
        schf.addRow("Image src:", self.sch_src); schf.addRow("Alt text:", self.sch_alt)
        self.sch_preview = _FitImageLabel(self.w_schematic)
        schf.addRow(self.sch_preview)
        self.subtabs.addTab(self.w_schematic, "Schematic")

        # ----- Layout
        self.w_layout = QWidget(); layf = QFormLayout(self.w_layout)
        self.lay_src = QLineEdit(); self.lay_alt = QLineEdit()
        self.lay_src.setPlaceholderText("../images/<PN>_components_top.png"); self.lay_alt.setPlaceholderText("Top view of miniPCB")
        self.lay_src.textChanged.connect(lambda *_: (self._on_dirty(True), self._maybe_refresh_image_preview("Layout")))
        self.lay_alt.textChanged.connect(lambda *_: self._on_dirty(True))
        layf.addRow("Image src:", self.lay_src); layf.addRow("Alt text:", self.lay_alt)
        self.lay_preview = _FitImageLabel(self.w_layout)
        layf.addRow(self.lay_preview)
        self.subtabs.addTab(self.w_layout, "Layout")

        # ----- Downloads
        self.tbl_downloads = self._make_table(["Text", "Href"])
        self.subtabs.addTab(self._wrap_table_with_buttons(self.tbl_downloads, tag="downloads"), "Downloads")

        # ----- Additional Resources
        self.tbl_resources = self._make_table(["Video URL"])
        self.subtabs.addTab(self._wrap_table_with_buttons(self.tbl_resources, tag="resources"), "Additional Resources")

        # ----- FMEA (single seed)
        self.w_fmea = QWidget(); vf = QVBoxLayout(self.w_fmea)
        self.txt_fmea_html = QTextEdit(); self.txt_fmea_html.setAcceptRichText(True); self.txt_fmea_html.setMinimumHeight(160)
        self.txt_fmea_html.textChanged.connect(lambda: self._on_dirty(True))
        vf.addWidget(self.txt_fmea_html, 1)
        self._seed_fmea = QTextEdit(); self._seed_fmea.setAcceptRichText(False); self._seed_fmea.setVisible(False)
        self._seed_fmea.textChanged.connect(lambda: self._on_dirty(True))
        vf.addWidget(self._seed_fmea)
        self.subtabs.addTab(self.w_fmea, "FMEA")

        # ----- Testing (DTP/ATP)
        self.w_testing = QWidget(); vt = QVBoxLayout(self.w_testing); vt.setSpacing(10)
        # DTP
        gb_dtp = QGroupBox("Developmental Test Plan (DTP)"); vdtp = QVBoxLayout(gb_dtp)
        self.txt_dtp_out = QTextEdit(); self.txt_dtp_out.setAcceptRichText(True); self.txt_dtp_out.setMinimumHeight(140)
        self.txt_dtp_out.textChanged.connect(lambda: self._on_dirty(True))
        vdtp.addWidget(self.txt_dtp_out)
        vt.addWidget(gb_dtp, 1)
        # ATP
        gb_atp = QGroupBox("Automated Test Plan (ATP)"); vatp = QVBoxLayout(gb_atp)
        self.txt_atp_out = QTextEdit(); self.txt_atp_out.setAcceptRichText(True); self.txt_atp_out.setMinimumHeight(140)
        self.txt_atp_out.textChanged.connect(lambda: self._on_dirty(True))
        vatp.addWidget(self.txt_atp_out)
        vt.addWidget(gb_atp, 1)
        # Hidden seeds
        self._seed_dtp = QTextEdit(); self._seed_dtp.setAcceptRichText(False); self._seed_dtp.setVisible(False); vt.addWidget(self._seed_dtp)
        self._seed_atp = QTextEdit(); self._seed_atp.setAcceptRichText(False); self._seed_atp.setVisible(False); vt.addWidget(self._seed_atp)
        self.subtabs.addTab(self.w_testing, "Testing")

        sv.addWidget(self.subtabs, 1)
        self.tabs.addTab(self.tab_sections, "Sections")

        # --------- Navigation tab
        self.tab_nav = QWidget(); nv = QVBoxLayout(self.tab_nav)
        self.tbl_nav = QTableWidget(0, 2)
        self.tbl_nav.setHorizontalHeaderLabels(["Text", "Href"])
        self.tbl_nav.verticalHeader().setVisible(False)
        self.tbl_nav.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_nav.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_nav.cellChanged.connect(lambda *_: self._on_dirty(True))
        nv.addWidget(self.tbl_nav, 1)
        rownav = QHBoxLayout()
        b_add = QPushButton("Add Link…")
        b_del = QPushButton("Remove Selected")
        b_up = QPushButton("Up")
        b_down = QPushButton("Down")
        b_add.clicked.connect(self._nav_add_link_dialog)
        b_del.clicked.connect(lambda: (self._nav_del_row(), self._on_dirty(True)))
        b_up.clicked.connect(lambda: (self._move_row(self.tbl_nav, -1), self._on_dirty(True)))
        b_down.clicked.connect(lambda: (self._move_row(self.tbl_nav, 1), self._on_dirty(True)))
        for b in (b_add, b_del, b_up, b_down):
            rownav.addWidget(b)
        rownav.addStretch(1)
        nv.addLayout(rownav)
        self.tabs.addTab(self.tab_nav, "Navigation")

        # --------- Review tab
        self.tab_review = QWidget(); rvw = QVBoxLayout(self.tab_review)
        self.review = QPlainTextEdit()
        self.review.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.review.textChanged.connect(lambda: self._on_dirty(True))
        rvw.addWidget(self.review, 1)
        self.tabs.addTab(self.tab_review, "Review")

        # --------- Stats tab
        self.tab_stats = QWidget(); sf = QFormLayout(self.tab_stats)
        self.stat_lines = QLabel("-"); self.stat_words = QLabel("-"); self.stat_chars = QLabel("-"); self.stat_edited = QLabel("-")
        sf.addRow("Line count:", self.stat_lines); sf.addRow("Word count:", self.stat_words)
        sf.addRow("Character count:", self.stat_chars); sf.addRow("Last edited:", self.stat_edited)
        self.tabs.addTab(self.tab_stats, "Stats")

        splitter.addWidget(right)
        splitter.setSizes([420, 980])
        self.setCentralWidget(splitter)

    # ---------- Status bar
    def _build_status(self):
        sb = QStatusBar(); self.setStatusBar(sb)
        sb.addPermanentWidget(QLabel(""))

    # ---------- Context menu (tree)
    def _on_tree_context(self, pos: QPoint):
        idx = self.explorer.indexAt(pos)
        self._last_context_index = idx if idx.isValid() else self.fs_model.index(str(self.ctx.root))

        menu = QMenu(self)
        act_new = QAction("New File…", self); act_new.triggered.connect(self._context_new_file)
        act_ren = QAction("Rename…", self); act_ren.triggered.connect(self._context_rename)
        act_del = QAction("Delete…", self); act_del.triggered.connect(self._context_delete)
        menu.addAction(act_new); menu.addAction(act_ren); menu.addAction(act_del)
        menu.exec_(self.explorer.viewport().mapToGlobal(pos))

    def _selected_file_paths(self) -> Tuple[List[Path], List[Path]]:
        sel = self.explorer.selectionModel().selectedIndexes()
        roots = [s for s in sel if s.column() == 0]
        paths: List[Path] = []; seen = set()
        for ix in roots:
            p = Path(self.fs_model.filePath(ix))
            if str(p) in seen: continue
            seen.add(str(p)); paths.append(p)
        files = [p for p in paths if p.is_file()]
        folders = [p for p in paths if p.is_dir()]
        return files, folders

    def _context_new_file(self):
        idx = self._last_context_index or self.fs_model.index(str(self.ctx.root))
        p = Path(self.fs_model.filePath(idx))
        target_dir = p if p.is_dir() else p.parent
        self._new_file_dialog(kind=None, target_dir=target_dir)

    def _context_rename(self):
        files, _ = self._selected_file_paths()
        files = [p for p in files if p.suffix.lower() in {".html",".htm",".md",".markdown"}]
        if not files:
            QMessageBox.information(self, "Rename", "Select one or more files to rename.")
            return
        if len(files) == 1:
            self._rename_single(files[0]); return
        self._rename_batch(files)

    def _context_delete(self):
        files, _ = self._selected_file_paths()
        files = [p for p in files if p.suffix.lower() in {".html",".htm",".md",".markdown"}]
        if not files:
            QMessageBox.information(self, "Delete", "Select one or more files to delete.")
            return
        count = len(files)
        names = "\n".join(str(p.relative_to(self.ctx.root)) for p in files[:10])
        extra = "" if count <= 10 else f"\n… and {count-10} more"
        resp = QMessageBox.question(self, "Delete files", f"Delete {count} file(s)?\n\n{names}{extra}",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if resp != QMessageBox.Yes: return
        errors = 0
        for p in files:
            try: p.unlink()
            except Exception: errors += 1
        self._update_file_count_status()
        self.explorer.setRootIndex(self.fs_model.index(str(self.ctx.root)))
        self._set_status("Delete completed" + (f" with {errors} error(s)" if errors else ""))

    # ---------- New file dialog
    def _new_file_dialog(self, kind: Optional[str], target_dir: Optional[Path]):
        if kind is None:
            box = QMessageBox(self)
            box.setWindowTitle("New File")
            box.setText("Create a new page:")
            board_btn = box.addButton("Board", QMessageBox.AcceptRole)
            coll_btn = box.addButton("Collection", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Cancel)
            box.exec_()
            clicked = box.clickedButton()
            if clicked == board_btn: kind = "board"
            elif clicked == coll_btn: kind = "collection"
            else: return

        base_dir = target_dir if target_dir else self.ctx.root

        if kind == "board":
            title, ok = QInputDialog.getText(self, "New Board", "Title:")
            if not ok or not title.strip(): return
            pn, ok = QInputDialog.getText(self, "New Board", "PN (e.g., 04B-005):")
            if not ok: return
            rev, ok = QInputDialog.getText(self, "New Board", "Rev (e.g., A1-01):")
            if not ok: return
            suggested = (base_dir / f"{pn.strip()}_{rev.strip()}.html").resolve()
            save_path, _ = QFileDialog.getSaveFileName(self, "Save Board Page As", str(suggested), "HTML (*.html)")
            if not save_path: return
            html = self.templates.render_board(title.strip(), pn.strip(), rev.strip())
            self.files.write_text(Path(save_path), html, WriteOptions(make_backup=False))
            self._set_status("Created new board page")
            self.explorer.setRootIndex(self.fs_model.index(str(self.ctx.root)))
            self._open_path(Path(save_path)); return

        if kind == "collection":
            title, ok = QInputDialog.getText(self, "New Collection", "Title:")
            if not ok or not title.strip(): return
            suggested = (base_dir / "collection.html").resolve()
            save_path, _ = QFileDialog.getSaveFileName(self, "Save Collection Page As", str(suggested), "HTML (*.html)")
            if not save_path: return
            html = self.templates.render_collection(title.strip())
            self.files.write_text(Path(save_path), html, WriteOptions(make_backup=False))
            self._set_status("Created new collection page")
            self.explorer.setRootIndex(self.fs_model.index(str(self.ctx.root)))
            self._open_path(Path(save_path)); return

    # ---------- Open / Save
    def _open_from_index(self, model_index):
        if not model_index.isValid(): return
        path = Path(self.fs_model.filePath(model_index))
        if path.is_dir(): return
        if path.suffix.lower() not in {".html",".htm",".md",".markdown"}: return
        self._open_path(path)

    def _open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open File", str(self.ctx.root),
                                              "Pages (*.html *.htm *.md *.markdown)")
        if path: self._open_path(Path(path))

    def _extract_section(self, html: str, sec_id: str) -> str:
        rx = re.compile(self._DIV_BY_ID_RX_FMT.format(id=re.escape(sec_id)), re.I | re.S)
        m = rx.search(html)
        return m.group("body") if m else ""

    def _open_path(self, path: Path):
        if self.dirty and self.current_path: self.save_current_page()
        try:
            text = self.files.read_text(path)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", f"{path}\n\n{e}"); return

        ext = path.suffix.lower()
        self.current_is_markdown = ext in {".md",".markdown"}

        self.current_path = path
        self.lbl_path.setText(str(path))

        if self.current_is_markdown:
            self._clear_editors()
            self.review.blockSignals(True); self.review.setPlainText(text); self.review.blockSignals(False)
            self.current_html = text
            self._on_dirty(False); self._set_status("Opened markdown")
            self._set_stats(path)
            self._update_autosave_label()
            return

        # Ensure sections exist
        html = text
        for sid in self._SECTION_IDS:
            html = self.html.ensure_section(html, sid)
        html = self.images.guess_and_set_defaults(path, html)
        self.current_html = html

        # ---- Metadata / header
        self.meta_title.setText(self.html.get_title(html))
        self.meta_keywords.setPlainText(self.html.get_keywords(html))
        self.meta_h1.setText(self._extract_h1(html))
        self.meta_slogan.setText(self._extract_slogan(html))

        # ---- Sections
        det_html = self._extract_section(html, "details")
        self._set_details_from_html(det_html)

        desc_html = self._extract_section(html, "description")
        self.txt_desc_generated.setHtml(desc_html)

        vids_html = self._extract_section(html, "videos")
        self._set_videos_from_html(vids_html)

        sch_html = self._extract_section(html, "schematic")
        self._set_image_fields_from_html(sch_html, which="schematic")

        lay_html = self._extract_section(html, "layout")
        self._set_image_fields_from_html(lay_html, which="layout")

        dls_html = self._extract_section(html, "downloads")
        self._set_downloads_from_html(dls_html)

        res_html = self._extract_section(html, "resources")
        self._set_resources_from_html(res_html)

        fmea_html = self._extract_section(html, "fmea")
        self.txt_fmea_html.setHtml(fmea_html)

        testing_html = self._extract_section(html, "testing")
        self._set_testing_from_html(testing_html)

        # ---- Seeds JSON
        seeds = self._read_ai_seeds_from_html(html)
        self._seed_desc.setPlainText(seeds.get("description_seed", "").strip())
        self._seed_fmea.setPlainText(seeds.get("fmea_seed", "").strip())
        self._seed_dtp.setPlainText(seeds.get("testing", {}).get("dtp_seed", "").strip())
        self._seed_atp.setPlainText(seeds.get("testing", {}).get("atp_seed", "").strip())

        # ---- Navigation links
        self._set_nav_from_html(html)

        # Source view
        self.review.blockSignals(True); self.review.setPlainText(html); self.review.blockSignals(False)

        self._on_dirty(False); self._set_status("Opened page"); self._set_stats(path)
        self._update_autosave_label()

        # Lazy previews if currently on those tabs
        self._maybe_refresh_image_preview(self.subtabs.tabText(self.subtabs.currentIndex()))

    def save_current_page(self):
        if not self.current_path: return

        if self.current_is_markdown:
            composed = self.review.toPlainText()
            try:
                self.files.write_text(self.current_path, composed, WriteOptions(make_backup=True, delete_backup_after_verify=True))
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"{self.current_path}\n\n{e}"); return
            self.current_html = composed; self._on_dirty(False); self._set_status("Saved")
            self._update_autosave_label()
            return

        html = self.current_html or ""

        # Title/keywords + header fields
        html = self.html.set_title(html, self.meta_title.text().strip())
        html = self.html.set_keywords(html, self.meta_keywords.toPlainText().strip())
        html = self._set_h1(html, self.meta_h1.text().strip())
        html = self._set_slogan(html, self.meta_slogan.text().strip())

        # Compose sections
        updates = {
            "details": self._compose_details_html(),
            "description": self.txt_desc_generated.toHtml(),
            "videos": self._compose_iframe_list_html(self.tbl_videos),
            "downloads": self._compose_downloads_html(self.tbl_downloads),
            "resources": self._compose_iframe_list_html(self.tbl_resources),
            "fmea": self.txt_fmea_html.toHtml(),
            "testing": self._compose_testing_html(),
            "schematic": self._compose_img_block(self.sch_src.text().strip(), self.sch_alt.text().strip()),
            "layout": self._compose_img_block(self.lay_src.text().strip(), self.lay_alt.text().strip()),
        }
        html = self.html.apply_sections(html, updates)

        # Write AI seeds JSON
        seeds = {
            "description_seed": self._seed_desc.toPlainText().strip(),
            "fmea_seed": self._seed_fmea.toPlainText().strip(),
            "testing": {
                "dtp_seed": self._seed_dtp.toPlainText().strip(),
                "atp_seed": self._seed_atp.toPlainText().strip()
            }
        }
        html = self._write_ai_seeds_to_html(html, seeds)

        # Write Navigation <ul class="nav-links">…</ul>
        html = self._write_nav_to_html(html)

        # Persist + reflect
        self.review.blockSignals(True); self.review.setPlainText(html); self.review.blockSignals(False)
        try:
            self.files.write_text(self.current_path, html, WriteOptions(make_backup=True, delete_backup_after_verify=True))
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"{self.current_path}\n\n{e}"); return

        self.current_html = html
        self._on_dirty(False)
        self._set_status("Saved")
        self._set_stats(self.current_path)
        self._update_autosave_label()

    # ---------- Clean / Prettify HTML (no form re-bind)
    def _update_html_formatting(self):
        if not self.current_path or self.current_is_markdown:
            QMessageBox.information(self, "Update HTML", "Open an HTML file first.")
            return
        pretty = self.html.prettify(self.current_html)
        if not pretty or pretty.strip() == self.current_html.strip():
            self._set_status("HTML already clean.")
            return
        self.current_html = pretty
        self.review.blockSignals(True); self.review.setPlainText(pretty); self.review.blockSignals(False)
        self._on_dirty(True)
        self._set_status("HTML formatted (unsaved)")

    # ---------- Populate helpers
    def _clear_editors(self):
        self.meta_title.clear(); self.meta_keywords.clear(); self.meta_desc.clear(); self.meta_h1.clear(); self.meta_slogan.clear()
        for ed in (self.det_part, self.det_title, self.det_board, self.det_pieces, self.det_panel):
            ed.clear()
        self.txt_desc_generated.clear()
        self.txt_fmea_html.clear()
        self.txt_dtp_out.clear(); self.txt_atp_out.clear()
        self.sch_src.clear(); self.sch_alt.clear(); self.sch_preview.setText("")
        self.lay_src.clear(); self.lay_alt.clear(); self.lay_preview.setText("")
        self._seed_desc.clear(); self._seed_fmea.clear(); self._seed_dtp.clear(); self._seed_atp.clear()
        for tbl in (self.tbl_videos, self.tbl_resources, self.tbl_downloads, self.tbl_nav):
            tbl.setRowCount(0)

    def _set_details_from_html(self, html_fragment: str):
        def _grab(label):
            m = re.search(rf"<strong>\s*{re.escape(label)}\s*:\s*</strong>\s*([^<]+)", html_fragment, re.I)
            return (m.group(1).strip() if m else "")
        self.det_part.setText(_grab("Part No"))
        self.det_title.setText(_grab("Title"))
        self.det_board.setText(_grab("Board Size"))
        self.det_pieces.setText(_grab("Pieces per Panel"))
        self.det_panel.setText(_grab("Panel Size"))

    def _set_videos_from_html(self, html_fragment: str):
        self.tbl_videos.setRowCount(0)
        for m in self._IFRAME_SRC_RX.finditer(html_fragment or ""):
            r = self.tbl_videos.rowCount(); self.tbl_videos.insertRow(r)
            self.tbl_videos.setItem(r, 0, QTableWidgetItem(m.group(1)))

    def _set_resources_from_html(self, html_fragment: str):
        self.tbl_resources.setRowCount(0)
        for m in self._IFRAME_SRC_RX.finditer(html_fragment or ""):
            r = self.tbl_resources.rowCount(); self.tbl_resources.insertRow(r)
            self.tbl_resources.setItem(r, 0, QTableWidgetItem(m.group(1)))

    def _set_downloads_from_html(self, html_fragment: str):
        self.tbl_downloads.setRowCount(0)
        for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_fragment or "", re.I | re.S):
            href, text = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
            r = self.tbl_downloads.rowCount(); self.tbl_downloads.insertRow(r)
            self.tbl_downloads.setItem(r, 0, QTableWidgetItem(text or href))
            self.tbl_downloads.setItem(r, 1, QTableWidgetItem(href))

    def _set_image_fields_from_html(self, section_html: str, which: str):
        src = ""; alt = ""
        m = self._IMG_SRC_RX.search(section_html or "")
        if m: src = m.group(1).strip()
        m = self._IMG_ALT_RX.search(section_html or "")
        if m: alt = m.group(1).strip()
        if which == "schematic":
            self.sch_src.setText(src); self.sch_alt.setText(alt)
        else:
            self.lay_src.setText(src); self.lay_alt.setText(alt)

    def _set_testing_from_html(self, testing_html: str):
        dtp_out = ""
        atp_out = ""
        blocks = re.split(r'(<h3[^>]*>.*?</h3>)', testing_html or "", flags=re.I | re.S)
        if len(blocks) <= 1:
            dtp_out = testing_html or ""
        else:
            current = None
            for chunk in blocks:
                if re.search(r'Developmental\s+Test\s+Plan', chunk, re.I):
                    current = "dtp"; continue
                if re.search(r'Automated\s+Test\s+Plan', chunk, re.I):
                    current = "atp"; continue
                if current == "dtp": dtp_out += chunk
                elif current == "atp": atp_out += chunk
        self.txt_dtp_out.setHtml((dtp_out or "").strip())
        self.txt_atp_out.setHtml((atp_out or "").strip())

    # ---------- Navigation parse/save
    def _set_nav_from_html(self, html: str):
        self.tbl_nav.setRowCount(0)
        m = self._NAV_UL_RX.search(html)
        if not m:
            return
        body = m.group("body")
        for a in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', body, re.I | re.S):
            href = a.group(1).strip()
            text = re.sub(r"\s+", " ", a.group(2)).strip()
            r = self.tbl_nav.rowCount()
            self.tbl_nav.insertRow(r)
            self.tbl_nav.setItem(r, 0, QTableWidgetItem(text or href))
            self.tbl_nav.setItem(r, 1, QTableWidgetItem(href or "#"))

    def _write_nav_to_html(self, html: str) -> str:
        items = []
        for r in range(self.tbl_nav.rowCount()):
            text = self.tbl_nav.item(r, 0).text().strip() if self.tbl_nav.item(r, 0) else ""
            href = self.tbl_nav.item(r, 1).text().strip() if self.tbl_nav.item(r, 1) else ""
            if not (text or href):
                continue
            items.append(f'<li><a href="{href or "#"}">{text or href or "Link"}</a></li>')
        new_body = "".join(items) if items else ""
        def repl(m):
            return m.group(1) + new_body + m.group(3)
        if self._NAV_UL_RX.search(html):
            return self._NAV_UL_RX.sub(repl, html, count=1)
        ul_block = f'<ul class="nav-links">{new_body}</ul>'
        if "</nav>" in html:
            return html.replace("</nav>", ul_block + "</nav>", 1)
        if "<body" in html:
            return re.sub(r'(<body[^>]*>)', r'\1<nav>' + ul_block + '</nav>', html, count=1, flags=re.I)
        return html

    # ---------- Compose helpers
    def _compose_details_html(self) -> str:
        def row(label, val): return f'<p><strong>{label}:</strong> {val}</p>' if val else ""
        return "".join([
            row("Part No", self.det_part.text().strip()),
            row("Title", self.det_title.text().strip()),
            row("Board Size", self.det_board.text().strip()),
            row("Pieces per Panel", self.det_pieces.text().strip()),
            row("Panel Size", self.det_panel.text().strip()),
        ])

    def _compose_iframe_list_html(self, tbl: QTableWidget) -> str:
        out = []
        for r in range(tbl.rowCount()):
            url = tbl.item(r, 0).text().strip() if tbl.item(r, 0) else ""
            if not url: continue
            out.append(f'<iframe src="{url}" loading="lazy" allowfullscreen></iframe>')
        return "\n".join(out)

    def _compose_downloads_html(self, tbl: QTableWidget) -> str:
        items = []
        for r in range(tbl.rowCount()):
            text = tbl.item(r, 0).text().strip() if tbl.item(r, 0) else ""
            href = tbl.item(r, 1).text().strip() if tbl.item(r, 1) else ""
            if not (text or href): continue
            a = f'<a href="{href or "#"}">{text or href or "Download"}</a>'
            items.append(f"<li>{a}</li>")
        return f"<ul>\n{''.join(items)}\n</ul>" if items else ""

    def _compose_img_block(self, src: str, alt: str) -> str:
        if not src:
            return ""
        return f'<div class="lightbox-container"><img src="{src}" loading="lazy" class="zoomable" alt="{alt}"></div>'

    def _compose_testing_html(self) -> str:
        dtp_html = self.txt_dtp_out.toHtml().strip()
        atp_html = self.txt_atp_out.toHtml().strip()
        parts = []
        if dtp_html:
            parts.append('<h3>Developmental Test Plan (DTP)</h3>')
            parts.append(dtp_html)
        if atp_html:
            parts.append('<h3>Automated Test Plan (ATP)</h3>')
            parts.append(atp_html)
        return "\n".join(parts)

    # ---------- Tables helpers
    def _make_table(self, headers: List[str]) -> QTableWidget:
        tbl = QTableWidget(0, len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        for i in range(len(headers)):
            mode = QHeaderView.Stretch if i == len(headers)-1 else QHeaderView.ResizeToContents
            tbl.horizontalHeader().setSectionResizeMode(i, mode)
        tbl.cellChanged.connect(lambda *_: self._on_dirty(True))
        return tbl

    def _wrap_table_with_buttons(self, tbl: QTableWidget, tag: str) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0,0,0,0)
        v.addWidget(tbl, 1)
        row = QHBoxLayout()
        b_add = QPushButton("Add"); b_add.clicked.connect(lambda: (tbl.insertRow(tbl.rowCount()), self._on_dirty(True)))
        b_del = QPushButton("Remove Selected")
        b_del.clicked.connect(lambda: (tbl.removeRow(tbl.currentRow()) if tbl.currentRow() >= 0 else None, self._on_dirty(True)))
        row.addWidget(b_add); row.addWidget(b_del); row.addStretch(1)
        v.addLayout(row)
        return w

    def _nav_del_row(self):
        r = self.tbl_nav.currentRow()
        if r >= 0: self.tbl_nav.removeRow(r)

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
        tbl.setCurrentCell(nr, 0)

    # ---------- Components visibility
    def _on_components_changed(self, *_):
        cfg = {
            "Description": self.chk_desc.isChecked(),
            "Videos": self.chk_videos.isChecked(),
            "Downloads": self.chk_downloads.isChecked(),
            "Additional Resources": self.chk_resources.isChecked(),
            "FMEA": self.chk_fmea.isChecked(),
            "Testing": self.chk_testing.isChecked(),
        }
        for i in range(self.subtabs.count()):
            name = self.subtabs.tabText(i)
            if name in cfg:
                if hasattr(self.subtabs, "setTabVisible"):
                    self.subtabs.setTabVisible(i, cfg[name])
                else:
                    self.subtabs.setTabEnabled(i, cfg[name])
        self._on_dirty(True)

    # ---------- Seed dialogs (top toolbar only)
    def _open_desc_seed_dialog(self):
        self._open_seed_dialog("Description", target=self._seed_desc)

    def _open_fmea_seed_dialog_single(self):
        self._open_seed_dialog("FMEA", target=self._seed_fmea)

    def _open_testing_seeds_dialog(self):
        dlg = QDialog(self); dlg.setWindowTitle("Edit Testing Seeds"); dlg.resize(760, 560)
        v = QVBoxLayout(dlg)
        grid = QGridLayout()
        lbl1 = QLabel("DTP Seed:"); lbl2 = QLabel("ATP Seed:")
        ed1 = QTextEdit(); ed1.setAcceptRichText(False); ed1.setPlainText(self._seed_dtp.toPlainText()); ed1.setMinimumHeight(200)
        ed2 = QTextEdit(); ed2.setAcceptRichText(False); ed2.setPlainText(self._seed_atp.toPlainText()); ed2.setMinimumHeight(200)
        grid.addWidget(lbl1, 0, 0); grid.addWidget(ed1, 0, 1)
        grid.addWidget(lbl2, 1, 0); grid.addWidget(ed2, 1, 1)
        v.addLayout(grid)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, dlg)
        v.addWidget(btns)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        if dlg.exec_() == QDialog.Accepted:
            self._seed_dtp.setPlainText(ed1.toPlainText().strip())
            self._seed_atp.setPlainText(ed2.toPlainText().strip())
            self._on_dirty(True)

    def _open_seed_dialog(self, label: str, target: QTextEdit):
        dlg = QDialog(self); dlg.setWindowTitle(f"Edit {label} Seed"); dlg.resize(760, 540)
        v = QVBoxLayout(dlg)
        info = QLabel(f"Enter seed notes for {label}. Plain text only.")
        info.setWordWrap(True); v.addWidget(info)
        ed = QTextEdit(); ed.setAcceptRichText(False); ed.setPlainText(target.toPlainText()); ed.setMinimumHeight(380)
        v.addWidget(ed, 1)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, dlg)
        v.addWidget(btns)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        if dlg.exec_() == QDialog.Accepted:
            target.setPlainText(ed.toPlainText().strip())
            self._on_dirty(True)

    # ---------- Autosave / Dirty / Stats
    def _on_dirty(self, dirty: bool):
        self.dirty = dirty
        self.ctx.bus.document_dirty.emit(dirty)
        self._countdown = self.autosave_seconds if dirty else 0
        title = constants.APP_NAME
        if self.current_path: title += " — " + str(self.current_path.name)
        if dirty: title += " *"
        self.setWindowTitle(title)
        self._update_autosave_label()

    def _tick_autosave(self):
        if not self.dirty or not self.current_path:
            self._update_autosave_label()
            return
        if self._countdown > 0:
            self._countdown -= 1
            self._update_autosave_label()
            return
        self.save_current_page()

    def _update_autosave_label(self):
        if self.dirty:
            self.lbl_autosave.setText(f"Autosave in {self._countdown}s")
        else:
            self.lbl_autosave.setText("Saved")

    def _set_status(self, msg: str):
        self.statusBar().showMessage(msg, 3_000)

    def _update_file_count_status(self):
        count = 0
        for ext in ("*.html","*.htm","*.md","*.markdown"):
            count += sum(1 for _ in self.ctx.root.rglob(ext))
        self._set_status(f"Ready • {count} HTML/Markdown files under {self.ctx.root}")

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

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.dirty:
            resp = QMessageBox.question(self, "Unsaved changes",
                                        "You have unsaved changes. Save before exiting?",
                                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                                        QMessageBox.Yes)
            if resp == QMessageBox.Cancel:
                event.ignore(); return
            if resp == QMessageBox.Yes:
                self.save_current_page()
        event.accept()

    # ---------- Rename helpers
    def _rename_single(self, path: Path):
        new_name, ok = QInputDialog.getText(self, "Rename file", "New file name:", text=path.name)
        if not ok or not new_name.strip(): return
        target = path.with_name(new_name.strip())
        if target.exists():
            QMessageBox.warning(self, "Rename", f"Target already exists:\n{target}"); return
        try:
            path.rename(target)
        except Exception as e:
            QMessageBox.critical(self, "Rename failed", f"{e}"); return
        self.explorer.setRootIndex(self.fs_model.index(str(self.ctx.root)))
        if self.current_path and self.current_path == path:
            self._open_path(target)
        self._set_status("Renamed 1 file.")

    def _rename_batch(self, files: List[Path]):
        find, ok = QInputDialog.getText(self, "Batch rename", "Find (substring or regex):")
        if not ok: return
        repl, ok = QInputDialog.getText(self, "Batch rename", "Replace with:")
        if not ok: return
        use_regex = True
        try: rx = re.compile(find)
        except re.error: use_regex = False

        preview = []
        for p in files:
            name = p.name
            new = rx.sub(repl, name) if use_regex else name.replace(find, repl)
            if new != name:
                preview.append((p, p.with_name(new)))
        if not preview:
            QMessageBox.information(self, "Batch rename", "No filenames changed with the provided pattern."); return
        conflicts = [t for (_, t) in preview if t.exists() and t not in [o for (o, _) in preview]]
        if conflicts:
            QMessageBox.warning(self, "Batch rename", f"{len(conflicts)} target name(s) already exist."); return

        sample = "\n".join(f"{o.name}  →  {t.name}" for (o, t) in preview[:10])
        extra = "" if len(preview) <= 10 else f"\n… and {len(preview)-10} more"
        resp = QMessageBox.question(self, "Apply batch rename", f"Rename {len(preview)} file(s)?\n\n{sample}{extra}",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if resp != QMessageBox.Yes: return
        errors = 0
        for (o, t) in preview:
            try: o.rename(t)
            except Exception: errors += 1
        self.explorer.setRootIndex(self.fs_model.index(str(self.ctx.root)))
        self._update_file_count_status()
        self._set_status("Batch rename done" + (f" with {errors} error(s)" if errors else ""))

    # ---------- Image preview + resolve
    def _on_subtab_changed(self, idx: int):
        name = self.subtabs.tabText(idx)
        self._maybe_refresh_image_preview(name)

    def _resolve_image_path(self, p: str) -> str:
        p = (p or "").strip()
        if not p:
            return ""
        if self.current_path and not Path(p).is_absolute():
            return str((self.current_path.parent / p).resolve())
        return p

    def _maybe_refresh_image_preview(self, name: str):
        if name == "Schematic":
            self.sch_preview.set_image_path(self._resolve_image_path(self.sch_src.text()))
        elif name == "Layout":
            self.lay_preview.set_image_path(self._resolve_image_path(self.lay_src.text()))

    # ---------- H1 / Slogan helpers
    def _extract_h1(self, html: str) -> str:
        m = re.search(r'<header[^>]*>\s*<h1[^>]*>(.*?)</h1>', html, re.I | re.S)
        if m: return re.sub(r'\s+', ' ', m.group(1)).strip()
        m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.I | re.S)
        return re.sub(r'\s+', ' ', m.group(1)).strip() if m else ""

    def _extract_slogan(self, html: str) -> str:
        m = re.search(r'<p[^>]*class=["\']slogan["\'][^>]*>(.*?)</p>', html, re.I | re.S)
        return re.sub(r'\s+', ' ', m.group(1)).strip() if m else ""

    def _set_h1(self, html: str, text: str) -> str:
        def repl(m): return m.group(1) + text + m.group(3)
        m = re.search(r'(<header[^>]*>\s*<h1[^>]*>)(.*?)(</h1>)', html, re.I | re.S)
        if m: return re.sub(r'(<header[^>]*>\s*<h1[^>]*>)(.*?)(</h1>)', repl, html, count=1, flags=re.I | re.S)
        m = re.search(r'(<h1[^>]*>)(.*?)(</h1>)', html, re.I | re.S)
        if m: return re.sub(r'(<h1[^>]*>)(.*?)(</h1>)', repl, html, count=1, flags=re.I | re.S)
        return html

    def _set_slogan(self, html: str, text: str) -> str:
        def repl(m): return m.group(1) + text + m.group(3)
        m = re.search(r'(<p[^>]*class=["\']slogan["\'][^>]*>)(.*?)(</p>)', html, re.I | re.S)
        if m: return re.sub(r'(<p[^>]*class=["\']slogan["\'][^>]*>)(.*?)(</p>)', repl, html, count=1, flags=re.I | re.S)
        return html

    # ---------- AI seeds helpers
    def _read_ai_seeds_from_html(self, html: str) -> Dict[str, Any]:
        m = self._SEEDS_SCRIPT_RX.search(html)
        if not m:
            return {"description_seed": "", "fmea_seed": "", "testing": {"dtp_seed": "", "atp_seed": ""}}
        try:
            data = json.loads(m.group(2).strip())
            fmea_seed = data.get("fmea_seed")
            if fmea_seed is None:
                fmea_obj = data.get("fmea", {})
                parts = [fmea_obj.get(k, "") for k in ("L0", "L1", "L2", "L3")]
                fmea_seed = "\n\n".join([p for p in parts if p.strip()])
            testing = data.get("testing", {})
            return {
                "description_seed": data.get("description_seed", ""),
                "fmea_seed": fmea_seed or "",
                "testing": {
                    "dtp_seed": testing.get("dtp_seed", ""),
                    "atp_seed": testing.get("atp_seed", "")
                }
            }
        except Exception:
            return {"description_seed": "", "fmea_seed": "", "testing": {"dtp_seed": "", "atp_seed": ""}}

    def _write_ai_seeds_to_html(self, html: str, seeds: Dict[str, Any]) -> str:
        payload = {
            "description_seed": seeds.get("description_seed", ""),
            "fmea_seed": seeds.get("fmea_seed", ""),
            "testing": {
                "dtp_seed": seeds.get("testing", {}).get("dtp_seed", ""),
                "atp_seed": seeds.get("testing", {}).get("atp_seed", "")
            }
        }
        json_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        m = self._SEEDS_SCRIPT_RX.search(html)
        if not m:
            block = f'\n<div id="ai-seeds" class="tab-content" data-hidden="true">\n  <script type="application/json" id="ai-seeds-json">{json_text}</script>\n</div>\n'
            if "</main>" in html:
                return html.replace("</main>", block + "</main>", 1)
            if "</body>" in html:
                return html.replace("</body>", block + "</body>", 1)
            return html + block
        return html[:m.start(2)] + json_text + html[m.end(2):]

    # ---------- Navigation: Add Link dialog with filtering
    def _nav_add_link_dialog(self):
        if not self.ctx.root or not self.ctx.root.exists():
            QMessageBox.warning(self, "Add Link", "Site root not found."); return

        dlg = QDialog(self); dlg.setWindowTitle("Add Navigation Link"); dlg.resize(820, 600)
        v = QVBoxLayout(dlg)

        # Filters
        filt_row = QHBoxLayout()
        edt_search = QLineEdit(); edt_search.setPlaceholderText("Search by filename or title…")
        cmb_ext = QComboBox(); cmb_ext.addItems(["All", "HTML", "Markdown"])
        filt_row.addWidget(QLabel("Filter:"))
        filt_row.addWidget(edt_search, 1)
        filt_row.addWidget(QLabel("Type:"))
        filt_row.addWidget(cmb_ext)
        v.addLayout(filt_row)

        lst = QListWidget(); v.addWidget(lst, 1)

        frm = QFormLayout()
        out_text = QLineEdit()
        out_href = QLineEdit()
        frm.addRow("Text:", out_text)
        frm.addRow("Href:", out_href)
        v.addLayout(frm)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, dlg)
        v.addWidget(btns)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)

        all_files: List[Path] = []
        for pat in ("*.html","*.htm","*.md","*.markdown"):
            all_files.extend(sorted(self.ctx.root.rglob(pat)))

        title_cache: Dict[Path, str] = {}
        title_rx = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)

        def _get_title(p: Path) -> str:
            if p in title_cache: return title_cache[p]
            t = ""
            try:
                if p.suffix.lower() in {".html",".htm"}:
                    txt = p.read_text("utf-8", errors="ignore")
                    m = title_rx.search(txt)
                    if m:
                        t = re.sub(r"\s+", " ", m.group(1)).strip()
            except Exception:
                t = ""
            title_cache[p] = t
            return t

        def _ext_ok(p: Path) -> bool:
            if cmb_ext.currentText() == "All": return True
            if cmb_ext.currentText() == "HTML": return p.suffix.lower() in {".html",".htm"}
            if cmb_ext.currentText() == "Markdown": return p.suffix.lower() in {".md",".markdown"}
            return True

        def _score(p: Path) -> int:
            name = p.name.lower()
            if name == "index.html": return -100
            if "index" in name: return -50
            return 0

        def _apply_filter():
            lst.clear()
            q = edt_search.text().strip().lower()
            items = []
            for p in all_files:
                if not _ext_ok(p): continue
                rel = p.relative_to(self.ctx.root)
                title = _get_title(p)
                text = f"{rel.as_posix()} — {title}" if title else rel.as_posix()
                if q and q not in text.lower(): continue
                items.append((p, text))
            items.sort(key=lambda t: (_score(t[0]), t[1].lower()))
            for p, text in items:
                it = QListWidgetItem(text)
                it.setData(Qt.UserRole, str(p))
                lst.addItem(it)

        _apply_filter()
        edt_search.textChanged.connect(_apply_filter)
        cmb_ext.currentIndexChanged.connect(_apply_filter)

        def _on_select():
            it = lst.currentItem()
            if not it: return
            p = Path(it.data(Qt.UserRole))
            rel = p.relative_to(self.ctx.root)
            title = _get_title(p)
            out_text.setText(title or p.stem)
            href = _rel_href(self.current_path or p, self.ctx.root, rel)
            out_href.setText(href)
        lst.currentItemChanged.connect(lambda *_: _on_select())
        if lst.count() > 0: lst.setCurrentRow(0)

        if dlg.exec_() == QDialog.Accepted:
            text = out_text.text().strip()
            href = out_href.text().strip()
            if not (text or href): return
            r = self.tbl_nav.rowCount(); self.tbl_nav.insertRow(r)
            self.tbl_nav.setItem(r, 0, QTableWidgetItem(text or href))
            self.tbl_nav.setItem(r, 1, QTableWidgetItem(href or "#"))
            self._on_dirty(True)

    # ---------- Part change (suggest default image filenames)
    def _on_part_changed(self, *_):
        pn = (self.det_part.text() or "").strip()
        if not pn: return
        if not self.sch_src.text().strip():
            self.sch_src.setText(f"../images/{pn}_schematic_01.png")
        if not self.lay_src.text().strip():
            self.lay_src.setText(f"../images/{pn}_components_top.png")
        self._maybe_refresh_image_preview(self.subtabs.tabText(self.subtabs.currentIndex()))
        self._on_dirty(True)

    # ---------- Generation helpers (simple ETA countdown + stub results)
    def _estimate_eta_seconds(self, seed_text: str, bonus_chars: int = 0) -> int:
        # Heuristic: 2s base + ~1s per 80 chars, capped 60s; favor seeds and current size
        count = len(seed_text or "")
        approx = 2 + (count + bonus_chars) // 80
        return max(2, min(int(approx), 60))

    def _countdown(self, label: QLabel, secs: int, done_cb: Callable[[], None]):
        label.setText(f"ETA: {secs}s")
        timer = QTimer(self)
        timer.setInterval(1000)
        state = {"remaining": secs}
        def _tick():
            state["remaining"] -= 1
            if state["remaining"] <= 0:
                timer.stop()
                label.setText("AI: done")
                done_cb()
            else:
                label.setText(f"ETA: {state['remaining']}s")
        timer.timeout.connect(_tick)
        timer.start()

    def _gen_description(self):
        seed = self._seed_desc.toPlainText().strip()
        eta = self._estimate_eta_seconds(seed, bonus_chars=len(self.txt_desc_generated.toPlainText()))
        self.lbl_desc_ai.setText(f"ETA: {eta}s")
        def _done():
            # Simple stub content using seed; real system would call out to a model
            if seed:
                self.txt_desc_generated.append(f"<p><em>Seed-based expansion ({_now_stamp()}):</em> {seed}</p>")
            else:
                self.txt_desc_generated.append(f"<p><em>Auto-generated ({_now_stamp()}):</em> Midband gain, biasing, and bandwidth trade-offs are explained with typical values.</p>")
            self._on_dirty(True)
        self._countdown(self.lbl_desc_ai, eta, _done)

    def _gen_fmea(self):
        seed = self._seed_fmea.toPlainText().strip()
        eta = self._estimate_eta_seconds(seed, bonus_chars=len(self.txt_fmea_html.toPlainText()))
        self.lbl_fmea_ai.setText(f"ETA: {eta}s")
        def _done():
            base = "<h3>FMEA</h3>"
            body = f"<p>{seed}</p>" if seed else "<p>Generated FMEA notes placeholder.</p>"
            self.txt_fmea_html.append(base + body)
            self._on_dirty(True)
        self._countdown(self.lbl_fmea_ai, eta, _done)

    def _gen_dtp(self):
        seed = self._seed_dtp.toPlainText().strip()
        eta = self._estimate_eta_seconds(seed, bonus_chars=len(self.txt_dtp_out.toPlainText()))
        self.lbl_dtp_ai.setText(f"ETA: {eta}s")
        def _done():
            self.txt_dtp_out.append(f"<p><strong>Update {_now_stamp()}:</strong> {seed or 'Generated DTP steps placeholder.'}</p>")
            self._on_dirty(True)
        self._countdown(self.lbl_dtp_ai, eta, _done)

    def _gen_atp(self):
        seed = self._seed_atp.toPlainText().strip()
        eta = self._estimate_eta_seconds(seed, bonus_chars=len(self.txt_atp_out.toPlainText()))
        self.lbl_atp_ai.setText(f"ETA: {eta}s")
        def _done():
            self.txt_atp_out.append(f"<p><strong>Update {_now_stamp()}:</strong> {seed or 'Generated ATP outline placeholder.'}</p>")
            self._on_dirty(True)
        self._countdown(self.lbl_atp_ai, eta, _done)
