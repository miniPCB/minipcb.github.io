#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
miniPCB Catalog — PyQt5
- FMEA Seeds moved to dialog (no inline seed editors on the FMEA tab)
- Description Seed moved to dialog (no inline seed editor on the Description tab)
- All seeds (Description, FMEA L0-L3, Testing DTP/ATP) saved as hidden JSON
  inside a hidden tab-content <div id="ai-seeds" data-hidden="true"> (not listed in tab buttons)
- Testing tab: dedicated AI ETA + progress (separate for DTP and ATP)
- Clean, compact HTML formatter (tables one <tr> per line)
- Review tab renders current unsaved state
- Navigation picker, collection helpers, autosave, etc.
"""

from __future__ import annotations
import sys, os, re, json, shutil, subprocess, datetime, platform, time
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from urllib.parse import urlparse, unquote

# ---- HTML parsing
try:
    from bs4 import BeautifulSoup, Comment, NavigableString, Tag, Doctype
    BS4_AVAILABLE = True
except Exception:
    BeautifulSoup = None; Comment = None; NavigableString = None; Tag = None; Doctype = None; BS4_AVAILABLE = False

# ---- OpenAI (optional)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except Exception:
    OpenAI = None; OPENAI_AVAILABLE = False

from PyQt5.QtCore import Qt, QSortFilterProxyModel, QModelIndex, QSettings, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QKeySequence, QIcon, QPixmap, QPainter, QFont, QCursor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFileSystemModel, QTreeView, QToolBar, QAction, QFileDialog,
    QInputDialog, QMessageBox, QLabel, QAbstractItemView, QFormLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QSplitter, QTabWidget, QTextEdit, QStyleFactory, QMenu, QDialog,
    QListWidget, QListWidgetItem, QDialogButtonBox, QCheckBox, QProgressBar, QGridLayout
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
        f.setStyleStrategy(QFont.PreferAntialias)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignCenter, emoji)
    finally:
        p.end()
    return QIcon(pm)

# ---------- Pretty HTML formatter (compact tables) ----------
VOID_TAGS = {"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}
INLINE_KEEP_ONE_LINE = {"p","li","h1","h2","h3","h4","h5","h6","button","label","a","strong","em","span","code","pre","small","sup","sub"}
ATTR_ORDER = ["lang","charset","name","content","http-equiv","rel","type","href","src","async","defer",
              "id","class","role","aria-label","title","alt","width","height","target","referrerpolicy",
              "allow","allowfullscreen","frameborder","data-full","onclick","data-hidden"]

def _attrs_sorted(tag: Tag) -> List[Tuple[str, str]]:
    if not isinstance(tag, Tag): return []
    items = list(tag.attrs.items()); norm = []
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

        if name == "tr":
            buf = [_tag_open(node)[:-1] + ">"]
            for c in node.contents or []:
                if isinstance(c, NavigableString):
                    txt = _text_collapse(str(c))
                    if txt: buf.append(txt)
                elif isinstance(c, Tag):
                    if c.name in {"td","th"}:
                        inner = []
                        for g in c.contents or []:
                            if isinstance(g, NavigableString):
                                t = _text_collapse(str(g))
                                if t: inner.append(t)
                            elif isinstance(g, Tag):
                                inner.append(_tag_open(g)[:-1] + ">" + "".join(_text_collapse(str(x)) if isinstance(x, NavigableString) else str(x) for x in g.contents or []) + f"</{g.name}>")
                        buf.append(f"<{c.name}>" + " ".join(inner) + f"</{c.name}>")
                    else:
                        buf.append(_tag_open(c)[:-1] + ">" + "".join(_text_collapse(str(x)) if isinstance(x, NavigableString) else str(x) for x in c.contents or []) + f"</{c.name}>")
            buf.append(f"</{name}>")
            write("".join(buf)); return

        if name in {"thead","tbody","tfoot"}:
            write(_tag_open(node)); indent += 1
            for c in node.contents or []:
                if isinstance(c, NavigableString) and not _text_collapse(str(c)): continue
                emit(c)
            indent -= 1; write(f"</{name}>"); return

        if name == "table":
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

# ---------- AI Workers ----------
class BaseAIWorker(QThread):
    finished = pyqtSignal(dict)  # {ok,bundle/error,elapsed}
    def __init__(self, api_key: str, model_name: str, sys_prompt: str, user_prompt: str, timeout: int = 120):
        super().__init__()
        self.api_key = api_key; self.model = model_name
        self.sys_prompt = sys_prompt; self.user_prompt = user_prompt; self.timeout = timeout
    def run(self):
        start = time.time()
        try:
            if not OPENAI_AVAILABLE: raise RuntimeError("OpenAI SDK not installed. pip install openai")
            if not self.api_key: raise RuntimeError("OPENAI_API_KEY not set.")
            client = OpenAI(api_key=self.api_key)
            out_text = ""
            try:
                resp = client.responses.create(
                    model=self.model,
                    input=[{"role":"system","content":self.sys_prompt},{"role":"user","content":self.user_prompt}],
                    timeout=self.timeout
                )
                out_text = getattr(resp, "output_text", None) or ""
                if not out_text:
                    try: out_text = resp.output[0].content[0].text
                    except Exception: out_text = ""
            except Exception:
                cc = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role":"system","content":self.sys_prompt},{"role":"user","content":self.user_prompt}],
                    timeout=self.timeout
                )
                out_text = cc.choices[0].message.content or ""
            if not out_text: raise RuntimeError("Model returned empty content.")
            self.finished.emit({"ok": True, "bundle": out_text, "elapsed": time.time() - start})
        except Exception as e:
            self.finished.emit({"ok": False, "error": str(e), "elapsed": time.time() - start})

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
                    soup = BeautifulSoup(txt, "html.parser")
                    return (soup.title.string.strip() if soup.title and soup.title.string else "")
                m = re.search(r"<title>(.*?)</title>", txt, re.I | re.S)
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
        self.setWindowTitle("Select navigation links")
        self.resize(640, 520)
        v = QVBoxLayout(self)
        self.cb_include_parent = QCheckBox("Show only likely collections (folder landing pages)")
        self.cb_include_parent.setChecked(True); v.addWidget(self.cb_include_parent)
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

# ---------- Seed Builder dialog (L0-L3) ----------
class SeedBuilderDialog(QDialog):
    """
    Matrix of sources (rows) x levels (L0..L3) with checkboxes + custom prompts per level.
    Enforces: L1 seed usable by L2/L3; L2 seed by L3; L3 seed not used as source.
    """
    def __init__(self, parent, sources: Dict[str, str], defaults: Dict[str, List[str]]):
        super().__init__(parent)
        self.setWindowTitle("Build FMEA Seeds")
        self.resize(900, 640)
        v = QVBoxLayout(self)

        # Grid of checkboxes
        gb = QGroupBox("Select sources to consider at each level")
        grid = QGridLayout(gb); grid.setHorizontalSpacing(14); grid.setVerticalSpacing(6)
        levels = ["L0","L1","L2","L3"]
        grid.addWidget(QLabel(""), 0, 0)
        for c, lv in enumerate(levels, start=1):
            lbl = QLabel(lv); lbl.setStyleSheet("font-weight:600;"); grid.addWidget(lbl, 0, c)

        self.matrix: Dict[Tuple[str,str], QCheckBox] = {}
        row = 1
        for key, text in sources.items():
            lbl = QLabel(key); grid.addWidget(lbl, row, 0)
            for c, lv in enumerate(levels, start=1):
                cb = QCheckBox(); grid.addWidget(cb, row, c); self.matrix[(key, lv)] = cb
                if key in ("Seed L1", "Seed L2", "Seed L3"):
                    if key == "Seed L1" and lv not in ("L2","L3"): cb.setEnabled(False)
                    if key == "Seed L2" and lv not in ("L3",): cb.setEnabled(False)
                    if key == "Seed L3": cb.setEnabled(False)
            row += 1
        v.addWidget(gb)

        # Custom prompts per level
        prm = QGroupBox("Custom prompts (optional)")
        pv = QFormLayout(prm)
        self.prompts = {lv: QTextEdit() for lv in levels}
        for lv in levels:
            self.prompts[lv].setAcceptRichText(False); self.prompts[lv].setPlaceholderText(f"Add guidance for {lv}…"); self.prompts[lv].setMinimumHeight(60)
            pv.addRow(f"{lv} Prompt:", self.prompts[lv])
        v.addWidget(prm, 1)

        # Defaults
        for key, arr in (defaults or {}).items():
            for lv in arr:
                cb = self.matrix.get((key, lv))
                if cb and cb.isEnabled(): cb.setChecked(True)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        v.addWidget(btns); btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)

    def selections(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {"L0":[], "L1":[], "L2":[], "L3":[]}
        for (key, lv), cb in self.matrix.items():
            if cb.isChecked() and cb.isEnabled(): out[lv].append(key)
        prompts = {lv: self.prompts[lv].toPlainText().strip() for lv in self.prompts}
        return {"sources_by_level": out, "prompts": prompts}

# ---------- Description Seed dialog (new) ----------
class DescriptionSeedDialog(QDialog):
    """Compact single-seed editor with snapshot history and Save→HTML."""
    def __init__(self, parent, initial: str):
        super().__init__(parent)
        self.setWindowTitle("Description Seed")
        self.resize(800, 560)
        v = QVBoxLayout(self)

        self.ed = QTextEdit(); self.ed.setAcceptRichText(False); self.ed.setMinimumHeight(260); self.ed.setPlaceholderText("Seed/context for AI product description…")
        self.ed.setPlainText(initial or "")
        v.addWidget(self.ed, 1)

        row = QHBoxLayout()
        self.btn_snapshot = QPushButton("Snapshot")
        self.btn_save_html = QPushButton("Save Seed → HTML")
        row.addWidget(self.btn_snapshot); row.addWidget(self.btn_save_html); row.addStretch(1)
        v.addLayout(row)

        gb = QGroupBox("Seed History (double-click to load)"); hv = QVBoxLayout(gb)
        self.history = QListWidget(); hv.addWidget(self.history, 1); v.addWidget(gb, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Close, Qt.Horizontal, self); v.addWidget(btns)
        btns.rejected.connect(self.reject)

        self.btn_snapshot.clicked.connect(self._do_snapshot)
        self.btn_save_html.clicked.connect(self._save_html)
        self.history.itemDoubleClicked.connect(self._load_from_history)
        self._do_snapshot(label="Loaded")

    def value(self) -> str:
        return self.ed.toPlainText().strip()

    def _do_snapshot(self, label: Optional[str] = None):
        lab = label or (f"Snapshot {today_iso()} {datetime.datetime.now().strftime('%H:%M:%S')}")
        item = QListWidgetItem(lab); item.setData(Qt.UserRole, self.value()); self.history.insertItem(0, item)

    def _load_from_history(self, item: QListWidgetItem):
        try:
            self.ed.setPlainText(item.data(Qt.UserRole))
        except Exception: pass

    def _save_html(self):
        if hasattr(self.parent(), "_save_description_seed_from_dialog"):
            self.parent()._save_description_seed_from_dialog(self.value())

# ---------- FMEA Seeds dialog (updated; dialog-only) ----------
class FMEASeedsDialog(QDialog):
    """
    Editor for L0-L3 seeds + matrix builder, snapshots, Save→HTML.
    """
    def __init__(self, parent, initial: Dict[str, str], get_sources_callable):
        super().__init__(parent)
        self.setWindowTitle("FMEA Seeds")
        self.resize(900, 680)
        self._get_sources = get_sources_callable

        v = QVBoxLayout(self)
        form = QFormLayout()
        self.ed_l0 = QTextEdit(); self.ed_l1 = QTextEdit(); self.ed_l2 = QTextEdit(); self.ed_l3 = QTextEdit()
        for ed in (self.ed_l0, self.ed_l1, self.ed_l2, self.ed_l3):
            ed.setAcceptRichText(False); ed.setMinimumHeight(90)
        self.ed_l0.setPlainText((initial or {}).get("L0",""))
        self.ed_l1.setPlainText((initial or {}).get("L1",""))
        self.ed_l2.setPlainText((initial or {}).get("L2",""))
        self.ed_l3.setPlainText((initial or {}).get("L3",""))
        form.addRow("Seed L0:", self.ed_l0); form.addRow("Seed L1:", self.ed_l1); form.addRow("Seed L2:", self.ed_l2); form.addRow("Seed L3:", self.ed_l3)
        v.addLayout(form)

        row = QHBoxLayout()
        self.btn_build = QPushButton("Build Seeds…")
        self.btn_snapshot = QPushButton("Snapshot")
        self.btn_save_html = QPushButton("Save Seeds → HTML")
        row.addWidget(self.btn_build); row.addSpacing(8); row.addWidget(self.btn_snapshot); row.addWidget(self.btn_save_html); row.addStretch(1)
        v.addLayout(row)

        gb = QGroupBox("Seed History (double-click to load)"); hv = QVBoxLayout(gb)
        self.history = QListWidget(); hv.addWidget(self.history, 1); v.addWidget(gb, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Close, Qt.Horizontal, self); v.addWidget(btns)
        btns.rejected.connect(self.reject)

        self.btn_build.clicked.connect(self._open_matrix_builder)
        self.btn_snapshot.clicked.connect(self._do_snapshot)
        self.btn_save_html.clicked.connect(self._save_html)
        self.history.itemDoubleClicked.connect(self._load_from_history)
        self._do_snapshot(label="Loaded")

    def value(self) -> Dict[str,str]:
        return {"L0": self.ed_l0.toPlainText().strip(), "L1": self.ed_l1.toPlainText().strip(),
                "L2": self.ed_l2.toPlainText().strip(), "L3": self.ed_l3.toPlainText().strip()}

    def _do_snapshot(self, label: Optional[str] = None):
        lab = label or (f"Snapshot {today_iso()} {datetime.datetime.now().strftime('%H:%M:%S')}")
        item = QListWidgetItem(lab); item.setData(Qt.UserRole, json.dumps(self.value(), ensure_ascii=False))
        self.history.insertItem(0, item)

    def _load_from_history(self, item: QListWidgetItem):
        try:
            obj = json.loads(item.data(Qt.UserRole))
            self.ed_l0.setPlainText(obj.get("L0","")); self.ed_l1.setPlainText(obj.get("L1",""))
            self.ed_l2.setPlainText(obj.get("L2","")); self.ed_l3.setPlainText(obj.get("L3",""))
        except Exception: pass

    def _open_matrix_builder(self):
        src, defaults = self._get_sources()
        dlg = SeedBuilderDialog(self, src, defaults); apply_windows_dark_titlebar(dlg)
        if dlg.exec_() != QDialog.Accepted: return
        sel = dlg.selections(); prompts = sel["prompts"]; levels = ["L0","L1","L2","L3"]; outputs: Dict[str,str] = {}
        if hasattr(self.parent(), "_start_seq_progress"): self.parent()._start_seq_progress("Building Seeds…", len(levels))
        try:
            for lv in levels:
                used = sel["sources_by_level"].get(lv, []); bundle = []
                for key, text in src.items():
                    if key in used and not key.startswith("Seed "):
                        if text: bundle.append(f"{key}:\n{text}")
                if "Seed L1" in used: bundle.append(f"Seed L1 (current):\n{outputs.get('L1','')}")
                if "Seed L2" in used: bundle.append(f"Seed L2 (current):\n{outputs.get('L2','')}")
                sys_prompt = ("You are assisting with an FMEA planning workflow. Produce a compact, neutral SEED NOTE.\n"
                              "Keep to 120-220 words. Plain text or minimal bullets. No HTML.")
                user = f"LEVEL: {lv}\nCUSTOM PROMPT:\n{prompts.get(lv,'')}\n\nMATERIAL:\n" + ("\n\n".join(bundle) if bundle else "(none)")
                worker = BaseAIWorker(self.parent().openai_key, self.parent().openai_model, sys_prompt, user, timeout=120)
                out = self.parent()._run_worker_blocking(worker)
                if not out.get("ok"):
                    self.parent()._error("Seed Builder", out.get("error","Unknown error")); return
                outputs[lv] = out["bundle"].strip()
                if hasattr(self.parent(), "_bump_seq_progress"): self.parent()._bump_seq_progress()
        finally:
            if hasattr(self.parent(), "_finish_seq_progress"): self.parent()._finish_seq_progress()

        self.ed_l0.setPlainText(outputs.get("L0","")); self.ed_l1.setPlainText(outputs.get("L1",""))
        self.ed_l2.setPlainText(outputs.get("L2","")); self.ed_l3.setPlainText(outputs.get("L3",""))
        self._do_snapshot(label=f"Built {today_iso()} {datetime.datetime.now().strftime('%H:%M:%S')}")

    def _save_html(self):
        if hasattr(self.parent(), "_save_fmea_seeds_from_dialog"):
            self.parent()._save_fmea_seeds_from_dialog(self.value())

# ---------- Main Window ----------
class CatalogWindow(QMainWindow):
    def __init__(self, content_root: Path, app_icon: QIcon):
        super().__init__()
        self.setWindowTitle(APP_TITLE); self.setWindowIcon(app_icon); self.resize(1480, 950)
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
        self._ai_target: Optional[str] = None  # 'desc' | 'fmea' | 'test-dtp' | 'test-atp'

        # Seeds (dialog-managed)
        self._seeds_fmea: Dict[str,str] = {"L0":"","L1":"","L2":"","L3":""}
        self._seed_desc: str = ""
        self._seed_dtp: str = ""
        self._seed_atp: str = ""

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
        self.act_refresh_icons = QAction("🔄 Refresh Icons", self)
        self.act_refresh_icons.triggered.connect(lambda: self.refresh_file_icons(light=False))
        tb.addAction(self.act_refresh_icons)
        tb.addSeparator()
        act_set_root = QAction("📁 Set Content Root…", self); act_set_root.triggered.connect(self.open_settings_dialog); tb.addAction(act_set_root)

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
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)

        # Right pane heading/status
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
        self.ed_title = QLineEdit(); self.ed_keywords = QTextEdit(); self.ed_keywords.setAcceptRichText(False); self.ed_keywords.setMinimumHeight(60)
        self.ed_description = QTextEdit(); self.ed_description.setAcceptRichText(False); self.ed_description.setMinimumHeight(90)
        self.ed_h1 = QLineEdit(); self.ed_slogan = QLineEdit()
        meta_form.addRow("Title:", self.ed_title); meta_form.addRow("Meta Keywords:", self.ed_keywords)
        meta_form.addRow("Meta Description:", self.ed_description); meta_form.addRow("H1:", self.ed_h1)
        meta_form.addRow("Slogan:", self.ed_slogan)
        self.tabs.addTab(self.meta_tab, "Metadata")

        # Sections host
        self.sections_host = QWidget(self); sh_v = QVBoxLayout(self.sections_host); sh_v.setContentsMargins(0,0,0,0); sh_v.setSpacing(8)

        # Page Components
        comp_box = QGroupBox("Page Components"); comp_row = QHBoxLayout(comp_box); comp_row.setSpacing(12)
        self.chk_desc = QCheckBox("Description"); self.chk_videos = QCheckBox("Videos")
        self.chk_downloads = QCheckBox("Downloads"); self.chk_resources = QCheckBox("Additional Resources")
        self.chk_fmea = QCheckBox("FMEA"); self.chk_testing = QCheckBox("Testing")
        for c in (self.chk_desc, self.chk_videos, self.chk_downloads, self.chk_resources, self.chk_fmea, self.chk_testing): c.setChecked(True)
        btn_show_all = QPushButton("Show All"); btn_hide_all = QPushButton("Hide All")
        btn_show_all.clicked.connect(lambda: self._set_all_components(True)); btn_hide_all.clicked.connect(lambda: self._set_all_components(False))
        for w in (self.chk_desc, self.chk_videos, self.chk_downloads, self.chk_resources, self.chk_fmea, self.chk_testing, btn_show_all, btn_hide_all): comp_row.addWidget(w)
        comp_row.addStretch(1)
        for c in (self.chk_desc, self.chk_videos, self.chk_downloads, self.chk_resources, self.chk_fmea, self.chk_testing):
            c.toggled.connect(self._on_components_changed)
        sh_v.addWidget(comp_box)

        # Sub-tabs (Sections container)
        self.sections_tabs = QTabWidget(self.sections_host); sh_v.addWidget(self.sections_tabs, 1)
        self.tabs.addTab(self.sections_host, "Sections")

        # Build section editors
        self._build_fixed_section_editors()

        # Navigation tab
        self.nav_host = QWidget(self); nv = QVBoxLayout(self.nav_host); nv.setContentsMargins(0,0,0,0)
        self.nav_tbl = QTableWidget(0, 2); self.nav_tbl.setHorizontalHeaderLabels(["Text", "Href"])
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

        # Review tab
        self.review_tab = QWidget(self); rv = QVBoxLayout(self.review_tab)
        self.review_raw = QTextEdit(self.review_tab); self.review_raw.setLineWrapMode(QTextEdit.NoWrap)
        self.review_raw.textChanged.connect(self._on_review_changed)
        rv.addWidget(self.review_raw)
        self.tabs.addTab(self.review_tab, "Review")
        self.tabs.currentChanged.connect(self._on_tabs_changed)

        # Stats tab
        self.stats_tab = QWidget(self); st = QFormLayout(self.stats_tab)
        self.stat_lines = QLabel("-"); self.stat_words = QLabel("-"); self.stat_chars = QLabel("-"); self.stat_edited = QLabel("-")
        st.addRow("Line count:", self.stat_lines); st.addRow("Word count:", self.stat_words)
        st.addRow("Character count:", self.stat_chars); st.addRow("Last edited:", self.stat_edited)
        self.tabs.addTab(self.stats_tab, "Stats")

        right_v.addWidget(self.tabs, 1)

        # Splitter
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self.tree); splitter.addWidget(right)
        splitter.setStretchFactor(0, 1); splitter.setStretchFactor(1, 2); splitter.setSizes([430, 1050])
        central = QWidget(self); outer = QHBoxLayout(central); outer.setContentsMargins(8,8,8,8); outer.setSpacing(8); outer.addWidget(splitter); self.setCentralWidget(central)

        self.apply_dark_styles(); apply_windows_dark_titlebar(self)
        self._set_dirty(False)

        if not BS4_AVAILABLE:
            self._info("BeautifulSoup not found", "Install with:\n\n  pip install beautifulsoup4")

    # --- Settings dialog ---
    def open_settings_dialog(self):
        settings = get_settings()
        cur = settings.value(KEY_CONTENT_DIR, str(default_content_root()))
        dlg = QFileDialog(self); dlg.setFileMode(QFileDialog.Directory); dlg.setOption(QFileDialog.ShowDirsOnly, True)
        dlg.setWindowTitle("Select Content Root (where your .html live)"); apply_windows_dark_titlebar(dlg)
        if cur and Path(cur).exists(): dlg.setDirectory(str(cur))
        if not dlg.exec_(): return
        sel = dlg.selectedFiles()
        if not sel: return
        root = Path(sel[0]); settings.setValue(KEY_CONTENT_DIR, str(root)); self.content_root = root
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
            QProgressBar { border:1px solid #3A3F44; border-radius:6px; text-align:center; }
        """)

    # ---------- AI (Testing: DTP/ATP) ----------
    def _start_test_ai(self, kind: str):
        """
        kind: 'dtp' or 'atp'
        Builds a prompt using page details + the corresponding seed, then calls the shared AI runner.
        """
        if self._ai_running: 
            return
        if not OPENAI_AVAILABLE:
            self._warn("OpenAI not installed", "pip install openai"); return
        if not self.openai_key:
            self._warn("API key required", "OpenAI API key not set."); return

        details = {
            "Part No": self.det_part.text().strip(),
            "Title": self.det_title.text().strip(),
            "Board Size": self.det_board.text().strip(),
            "Pieces per Panel": self.det_pieces.text().strip(),
            "Panel Size": self.det_panel.text().strip(),
        }
        pagectx = f"PAGE: title={self.ed_title.text().strip()} h1={self.ed_h1.text().strip()} part_no={details['Part No']}"

        if kind == "dtp":
            seed = self.dtp_seed.toPlainText().strip()
            sys_prompt = (
                "You are an experienced hardware test engineer. Produce a concise Developmental Test Plan (DTP) as HTML.\n"
                "Use <h3> section headings and a single <ul> list per section. No inline styles or scripts."
            )
            user = (
                f"{pagectx}\nDETAILS:\n{json.dumps(details, ensure_ascii=False)}\n"
                f"SEED (DTP):\n{seed}\n\n"
                "TASK:\nReturn ONLY an HTML fragment comprising headings and bullet lists of specific developmental tests, "
                "including measurement points (TP#…), instruments, and pass/fail cues."
            )
            # primes UI
            self.lbl_dtp_ai.setText("AI: starting…"); self.pb_dtp.show()
            target = "dtp"

        elif kind == "atp":
            seed = self.atp_seed.toPlainText().strip()
            sys_prompt = (
                "You are an experienced hardware and test-automation engineer. Produce an Automated Test Plan (ATP) as HTML.\n"
                "Use <h3> headings and <ul> lists. Call out step sequencing, stimulus, expected readings, and automation hooks. No inline styles."
            )
            user = (
                f"{pagectx}\nDETAILS:\n{json.dumps(details, ensure_ascii=False)}\n"
                f"SEED (ATP):\n{seed}\n\n"
                "TASK:\nReturn ONLY an HTML fragment with structured, automatable test steps. "
                "Include references to TPs, signal levels, scripts or SCPI calls when relevant."
            )
            self.lbl_atp_ai.setText("AI: starting…"); self.pb_atp.show()
            target = "atp"
        else:
            return

        self._kick_ai(sys_prompt, user, target=target)

    # ---------- Generic Seed dialog (DTP/ATP) ----------
    def _open_seed_dialog(self, label: str, target_textedit: QTextEdit):
        """
        Open a modal seed editor (for DTP/ATP). Switch to Schematic tab first, then restore afterwards.
        """
        prev_index = self.sections_tabs.currentIndex()
        try:
            schem_idx = self.sections_tabs.indexOf(self.w_schematic)
            if schem_idx != -1:
                self.sections_tabs.setCurrentIndex(schem_idx)
                QApplication.processEvents()
        except Exception:
            pass

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit {label} Seed")
        dlg.resize(780, 560)
        v = QVBoxLayout(dlg)

        info = QLabel(f"Enter seed notes for {label}. Plain text only.")
        info.setWordWrap(True)
        v.addWidget(info)

        ed = QTextEdit()
        ed.setAcceptRichText(False)
        ed.setPlainText(target_textedit.toPlainText().strip())
        ed.setMinimumHeight(400)
        v.addWidget(ed, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, dlg)
        v.addWidget(btns)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)

        try:
            apply_windows_dark_titlebar(dlg)
        except Exception:
            pass

        if dlg.exec_() == QDialog.Accepted:
            target_textedit.blockSignals(True)
            target_textedit.setPlainText(ed.toPlainText().strip())
            target_textedit.blockSignals(False)
            self._on_any_changed()

        try:
            if 0 <= prev_index < self.sections_tabs.count():
                self.sections_tabs.setCurrentIndex(prev_index)
        except Exception:
            pass

    # ---------- UI builders ----------
    def _build_fixed_section_editors(self):
        # ---------------- Details ----------------
        self.w_details = QWidget()
        det_form = QFormLayout(self.w_details); det_form.setVerticalSpacing(8)
        self.det_part = QLineEdit(); self.det_title = QLineEdit(); self.det_board = QLineEdit(); self.det_pieces = QLineEdit(); self.det_panel = QLineEdit()
        det_form.addRow("Part No:", self.det_part); det_form.addRow("Title:", self.det_title); det_form.addRow("Board Size:", self.det_board)
        det_form.addRow("Pieces per Panel:", self.det_pieces); det_form.addRow("Panel Size:", self.det_panel)
        for ed in (self.det_part, self.det_title, self.det_board, self.det_pieces, self.det_panel):
            ed.textChanged.connect(self._on_any_changed)
        self.det_part.textChanged.connect(self._on_part_changed)
        self.sections_tabs.addTab(self.w_details, "Details")

        # ---------------- Description ----------------
        self.w_desc = QWidget()
        vdesc = QVBoxLayout(self.w_desc); vdesc.setSpacing(8); vdesc.setContentsMargins(6,6,6,6)

        # Hidden (in-UI) seed storage: keep a QTextEdit but keep it invisible; editing occurs via dialog.
        self.desc_seed = QTextEdit()
        self.desc_seed.setAcceptRichText(False)
        self.desc_seed.setVisible(False)  # <-- seed editing moved to dialog
        self.desc_seed.textChanged.connect(self._on_any_changed)

        # AI-generated description display
        gen_box = QGroupBox("AI Generated")
        gen_v = QVBoxLayout(gen_box)
        self.desc_generated = QTextEdit()
        self.desc_generated.setReadOnly(True)
        self.desc_generated.setAcceptRichText(True)
        self.desc_generated.setMinimumHeight(160)
        gen_v.addWidget(self.desc_generated)

        # Controls
        controls = QHBoxLayout()
        self.btn_desc_seed_edit = QPushButton("Edit Seed…")
        self.btn_desc_seed_edit.clicked.connect(self._open_desc_seed_dialog)
        self.btn_desc_generate = QPushButton("Generate")
        self.btn_desc_generate.clicked.connect(self._start_desc_ai)

        self.lbl_desc_ai = QLabel("AI: idle"); self.lbl_desc_ai.setStyleSheet("color:#C8E6C9;")
        self.pb_desc = QProgressBar(); self.pb_desc.setMaximum(0); self.pb_desc.setValue(0); self.pb_desc.hide()

        controls.addWidget(self.btn_desc_seed_edit)
        controls.addWidget(self.btn_desc_generate)
        controls.addSpacing(12)
        controls.addWidget(self.lbl_desc_ai)
        controls.addStretch(1)
        controls.addWidget(self.pb_desc)

        vdesc.addLayout(controls)
        vdesc.addWidget(gen_box, 1)
        self.sections_tabs.addTab(self.w_desc, "Description")

        # ---------------- Videos (id="simulation") ----------------
        vids_widget = self._wrap_table_with_buttons(self._make_video_table(), "video")
        self.w_videos = vids_widget
        self.sections_tabs.addTab(self.w_videos, "Videos")

        # ---------------- Schematic ----------------
        self.w_schematic = QWidget(); schf = QFormLayout(self.w_schematic); schf.setVerticalSpacing(8)
        self.sch_src = QLineEdit(); self.sch_alt = QLineEdit()
        self.sch_src.setPlaceholderText("../images/<PN>_schematic_01.png"); self.sch_alt.setPlaceholderText("Schematic")
        self.sch_src.textChanged.connect(lambda *_: (self._update_preview('schematic'), self._on_any_changed()))
        self.sch_alt.textChanged.connect(self._on_any_changed)
        schf.addRow("Image src:", self.sch_src); schf.addRow("Alt text:", self.sch_alt)
        self.sch_preview = PreviewLabel(); schf.addRow("Preview:", self.sch_preview)
        self.sections_tabs.addTab(self.w_schematic, "Schematic")

        # ---------------- Layout ----------------
        self.w_layout = QWidget(); layf = QFormLayout(self.w_layout); layf.setVerticalSpacing(8)
        self.lay_src = QLineEdit(); self.lay_alt = QLineEdit()
        self.lay_src.setPlaceholderText("../images/<PN>_components_top.png"); self.lay_alt.setPlaceholderText("Top view of miniPCB")
        self.lay_src.textChanged.connect(lambda *_: (self._update_preview('layout'), self._on_any_changed()))
        self.lay_alt.textChanged.connect(self._on_any_changed)
        layf.addRow("Image src:", self.lay_src); layf.addRow("Alt text:", self.lay_alt)
        self.lay_preview = PreviewLabel(); layf.addRow("Preview:", self.lay_preview)
        self.sections_tabs.addTab(self.w_layout, "Layout")

        # ---------------- Downloads ----------------
        dls_widget = self._wrap_table_with_buttons(self._make_download_table(), "download")
        self.w_downloads = dls_widget
        self.sections_tabs.addTab(self.w_downloads, "Downloads")

        # ---------------- Additional Resources ----------------
        res_widget = self._wrap_table_with_buttons(self._make_resources_table(), "video")
        self.w_resources = res_widget
        self.sections_tabs.addTab(self.w_resources, "Additional Resources")

        # ---------------- FMEA (output + controls; seeds handled in separate dialog) ----------------
        self.w_fmea = QWidget(); vf = QVBoxLayout(self.w_fmea); vf.setSpacing(8); vf.setContentsMargins(6,6,6,6)

        # FMEA output (AI table)
        out_box = QGroupBox("AI FMEA Table (HTML)")
        ov = QVBoxLayout(out_box)
        self.fmea_html = QTextEdit()
        self.fmea_html.setAcceptRichText(True)
        self.fmea_html.setReadOnly(True)
        self.fmea_html.setMinimumHeight(220)
        ov.addWidget(self.fmea_html, 1)
        vf.addWidget(out_box, 2)

        # FMEA controls (open seeds dialog, snapshot, save seeds JSON to HTML)
        row_ai = QHBoxLayout()
        self.btn_seed_build = QPushButton("FMEA Seeds…")
        self.btn_seed_build.clicked.connect(self._open_seed_builder)  # opens the existing multi-level seed builder dialog

        self.btn_seed_snapshot = QPushButton("Snapshot Seeds")
        self.btn_seed_snapshot.clicked.connect(self._snapshot_seeds)

        self.btn_seed_save_html = QPushButton("Save Seeds → HTML")
        self.btn_seed_save_html.clicked.connect(self._save_seeds_to_html)

        # AI generation for FMEA table
        self.btn_fmea_generate = QPushButton("Generate FMEA with AI")
        self.btn_fmea_generate.clicked.connect(self._start_fmea_ai)
        self.lbl_fmea_ai = QLabel("AI: idle"); self.lbl_fmea_ai.setStyleSheet("color:#C8E6C9;")
        self.pb_fmea = QProgressBar(); self.pb_fmea.setMaximum(0); self.pb_fmea.setValue(0); self.pb_fmea.hide()

        row_ai.addWidget(self.btn_seed_build)
        row_ai.addWidget(self.btn_seed_snapshot)
        row_ai.addWidget(self.btn_seed_save_html)
        row_ai.addSpacing(16)
        row_ai.addWidget(self.btn_fmea_generate)
        row_ai.addSpacing(12)
        row_ai.addWidget(self.lbl_fmea_ai)
        row_ai.addStretch(1)
        row_ai.addWidget(self.pb_fmea)
        vf.addLayout(row_ai)

        # (Optional) simple seed history list (compact height). Keep if you were using it.
        hist_box = QGroupBox("Seed History (double-click to load)")
        hv = QVBoxLayout(hist_box)
        self.list_seed_history = QListWidget(); self.list_seed_history.itemDoubleClicked.connect(self._load_seed_history_item)
        hv.addWidget(self.list_seed_history, 1)
        vf.addWidget(hist_box, 1)

        self.sections_tabs.addTab(self.w_fmea, "FMEA")

        # ---------------- Testing (DTP & ATP) ----------------
        self.w_testing = QWidget()
        vt = QVBoxLayout(self.w_testing); vt.setContentsMargins(6,6,6,6); vt.setSpacing(10)

        # DTP
        gb_dtp = QGroupBox("Developmental Test Plan (DTP)")
        vdtp = QVBoxLayout(gb_dtp)

        # hidden DTP seed (edited via dialog)
        self.dtp_seed = QTextEdit(); self.dtp_seed.setAcceptRichText(False); self.dtp_seed.setVisible(False)
        self.dtp_seed.textChanged.connect(self._on_any_changed)

        self.dtp_generated = QTextEdit()
        self.dtp_generated.setAcceptRichText(True)
        self.dtp_generated.setReadOnly(True)
        self.dtp_generated.setMinimumHeight(160)

        ctrl_dtp = QHBoxLayout()
        self.btn_dtp_seed = QPushButton("Edit DTP Seed…")
        self.btn_dtp_seed.clicked.connect(lambda: self._open_seed_dialog("DTP", self.dtp_seed))

        self.btn_dtp_generate = QPushButton("Generate DTP")
        self.btn_dtp_generate.clicked.connect(lambda: self._start_test_ai("dtp"))

        self.lbl_dtp_ai = QLabel("AI: idle"); self.lbl_dtp_ai.setStyleSheet("color:#C8E6C9;")
        self.pb_dtp = QProgressBar(); self.pb_dtp.setMaximum(0); self.pb_dtp.setValue(0); self.pb_dtp.hide()

        ctrl_dtp.addWidget(self.btn_dtp_seed)
        ctrl_dtp.addWidget(self.btn_dtp_generate)
        ctrl_dtp.addSpacing(12)
        ctrl_dtp.addWidget(self.lbl_dtp_ai)
        ctrl_dtp.addStretch(1)
        ctrl_dtp.addWidget(self.pb_dtp)

        vdtp.addLayout(ctrl_dtp)
        vdtp.addWidget(self.dtp_generated, 1)
        vt.addWidget(gb_dtp, 1)

        # ATP
        gb_atp = QGroupBox("Automated Test Plan (ATP)")
        vatp = QVBoxLayout(gb_atp)

        # hidden ATP seed (edited via dialog)
        self.atp_seed = QTextEdit(); self.atp_seed.setAcceptRichText(False); self.atp_seed.setVisible(False)
        self.atp_seed.textChanged.connect(self._on_any_changed)

        self.atp_generated = QTextEdit()
        self.atp_generated.setAcceptRichText(True)
        self.atp_generated.setReadOnly(True)
        self.atp_generated.setMinimumHeight(160)

        ctrl_atp = QHBoxLayout()
        self.btn_atp_seed = QPushButton("Edit ATP Seed…")
        self.btn_atp_seed.clicked.connect(lambda: self._open_seed_dialog("ATP", self.atp_seed))

        self.btn_atp_generate = QPushButton("Generate ATP")
        self.btn_atp_generate.clicked.connect(lambda: self._start_test_ai("atp"))

        self.lbl_atp_ai = QLabel("AI: idle"); self.lbl_atp_ai.setStyleSheet("color:#C8E6C9;")
        self.pb_atp = QProgressBar(); self.pb_atp.setMaximum(0); self.pb_atp.setValue(0); self.pb_atp.hide()

        ctrl_atp.addWidget(self.btn_atp_seed)
        ctrl_atp.addWidget(self.btn_atp_generate)
        ctrl_atp.addSpacing(12)
        ctrl_atp.addWidget(self.lbl_atp_ai)
        ctrl_atp.addStretch(1)
        ctrl_atp.addWidget(self.pb_atp)

        vatp.addLayout(ctrl_atp)
        vatp.addWidget(self.atp_generated, 1)
        vt.addWidget(gb_atp, 1)

        self.sections_tabs.addTab(self.w_testing, "Testing")

        # ---------------- Page Components toggle wiring (existing) ----------------
        self._apply_component_visibility_to_editor()

    # ---------- Tables ----------
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
        for c in (self.chk_desc, self.chk_videos, self.chk_downloads, self.chk_resources, self.chk_fmea, self.chk_testing):
            c.setChecked(state)

    def _on_components_changed(self, _checked: bool):
        self._apply_component_visibility_to_editor(); self._on_any_changed()

    def _apply_component_visibility_to_editor(self):
        cfg = {
            self.w_desc: self.chk_desc.isChecked(),
            self.w_videos: self.chk_videos.isChecked(),
            self.w_downloads: self.chk_downloads.isChecked(),
            self.w_resources: self.chk_resources.isChecked(),
            self.w_fmea: self.chk_fmea.isChecked(),
            self.w_testing: self.chk_testing.isChecked(),
        }
        for w, on in cfg.items():
            idx = self.sections_tabs.indexOf(w)
            if hasattr(self.sections_tabs, "setTabVisible"):
                self.sections_tabs.setTabVisible(idx, on)
            else:
                self.sections_tabs.setTabEnabled(idx, on)

    # ---------- Context menus ----------
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

    def _tree_context_menu(self, pos):
        menu = QMenu(self)
        act_light = menu.addAction("Refresh Icons (Fast)")
        act_heavy = menu.addAction("Refresh Icons (Full)")
        act = menu.exec_(self.tree.viewport().mapToGlobal(pos))
        if act is act_light:
            self.refresh_file_icons(light=True)
        elif act is act_heavy:
            self.refresh_file_icons(light=False)

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
        idx_collection = self.tabs.indexOf(self.collection_host) if hasattr(self, "collection_host") else -1
        if hasattr(self.tabs, "setTabVisible"):
            self.tabs.setTabVisible(idx_sections, self.page_mode == "detail")
            if idx_collection >= 0: self.tabs.setTabVisible(idx_collection, self.page_mode == "collection")
        else:
            self.tabs.setTabEnabled(idx_sections, self.page_mode == "detail")
            if idx_collection >= 0: self.tabs.setTabEnabled(idx_collection, self.page_mode == "collection")

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
        if hasattr(self, "desc_generated"): self.desc_generated.clear()
        # Testing fields
        if hasattr(self, "dtp_seed"): self.dtp_seed.clear()
        if hasattr(self, "atp_seed"): self.atp_seed.clear()
        if hasattr(self, "dtp_text"): self.dtp_text.clear()
        if hasattr(self, "atp_text"): self.atp_text.clear()
        # FMEA output
        if hasattr(self, "fmea_html"): self.fmea_html.clear()
        self.review_raw.blockSignals(True); self.review_raw.clear(); self.review_raw.blockSignals(False)
        self._review_dirty = False
        self._set_ai_status_idle_all()
        # reset components default show
        for c in (getattr(self,'chk_desc',None), getattr(self,'chk_videos',None), getattr(self,'chk_downloads',None),
                  getattr(self,'chk_resources',None), getattr(self,'chk_fmea',None), getattr(self,'chk_testing',None)):
            if isinstance(c, QCheckBox): c.blockSignals(True); c.setChecked(True); c.blockSignals(False)
        self._apply_component_visibility_to_editor()
        # reset in-memory seeds (they will be loaded from HTML)
        self._seeds_fmea = {"L0":"","L1":"","L2":"","L3":""}
        self._seed_desc = ""; self._seed_dtp = ""; self._seed_atp = ""

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

        # Component flags
        f_desc, f_vids, f_dl, f_res, f_fmea, f_test = self._read_component_flags(soup)
        for chk, val in ((self.chk_desc,f_desc),(self.chk_videos,f_vids),(self.chk_downloads,f_dl),(self.chk_resources,f_res),(self.chk_fmea,f_fmea),(self.chk_testing,f_test)):
            chk.blockSignals(True); chk.setChecked(val); chk.blockSignals(False)
        self._apply_component_visibility_to_editor()

        # Description generated HTML (seed is hidden; do not try to read visible seed)
        desc_div = soup.find("div", class_="tab-content", id="description")
        gen_html = ""
        if desc_div:
            h3g = desc_div.find(["h3","h4"], string=re.compile(r"^\s*AI\s*Generated\s*$", re.I))
            gen_div = None
            if h3g: gen_div = h3g.find_next_sibling("div", class_="generated")
            if gen_div: gen_html = gen_div.decode_contents()
        self.desc_generated.setHtml(gen_html or "")

        # Videos / Resources
        self._populate_iframe_table(self.sim_table, soup.find("div", class_="tab-content", id="simulation"))
        self._populate_iframe_table(self.res_table, soup.find("div", class_="tab-content", id="resources"))

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

        # Load hidden seeds + FMEA table + Testing seeds/text
        self._load_hidden_seeds_from_soup(soup)

        fmea_div = soup.find("div", class_="tab-content", id="fmea")
        if fmea_div:
            tbl = fmea_div.find("table")
            if tbl: self.fmea_html.setHtml(str(tbl))

        test_div = soup.find("div", class_="tab-content", id="testing")
        if test_div:
            def _grab_after(h3_text):
                h = test_div.find(["h3","h2"], string=re.compile(rf"^\s*{re.escape(h3_text)}\s*$", re.I))
                if not h: return ""
                pre = h.find_next_sibling("pre")
                return pre.get_text() if pre else ""
            self.dtp_text.setPlainText(_grab_after("Developmental Test Plan (DTP)"))
            self.atp_text.setPlainText(_grab_after("Automated Test Plan (ATP)"))

        # Populate visible Testing seeds from hidden store
        self.dtp_seed.setPlainText(self._seed_dtp or "")
        self.atp_seed.setPlainText(self._seed_atp or "")

    def _read_component_flags(self, soup: BeautifulSoup):
        present = set()
        tabs = soup.find("div", class_="tabs")
        if tabs:
            for b in tabs.find_all("button", class_="tab"):
                oc = b.get("onclick",""); m = re.search(r"showTab\('([^']+)'", oc)
                if m: present.add(m.group(1))
        def exists(sec_id): return soup.find("div", id=sec_id, class_="tab-content") is not None
        f_desc = "description" in present if tabs else exists("description")
        f_vids = "simulation" in present if tabs else exists("simulation")
        f_dl   = "downloads"   in present if tabs else exists("downloads")
        f_res  = "resources"   in present if tabs else exists("resources")
        f_fmea = "fmea"        in present if tabs else exists("fmea")
        f_test = "testing"     in present if tabs else exists("testing")
        return f_desc, f_vids, f_dl, f_res, f_fmea, f_test

    def _load_collection_page_from_soup(self, soup: BeautifulSoup):
        title = (soup.title.string if soup.title and soup.title.string else "") if soup.title else ""
        self.ed_title.setText((title or "").strip())
        kw = soup.find("meta", attrs={"name":"keywords"})
        self.ed_keywords.setPlainText(kw["content"].strip() if kw and kw.has_attr("content") else "")
        desc = soup.find("meta", attrs={"name":"description"})
        self.ed_description.setPlainText(desc["content"].strip() if desc and desc.has_attr("content") else "")
        h1 = soup.find("h1"); self.ed_h1.setText(h1.get_text(strip=True) if h1 else "")
        slog = soup.find("p", class_="slogan"); self.ed_slogan.setText(slog.get_text(strip=True) if slog else "")

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

        # Pull existing rows:
        main = soup.find("main"); tbl = None
        if main: tbl = main.find("table")
        if not tbl: tbl = soup.find("table")
        self.collection_tbl.blockSignals(True); self.collection_tbl.setRowCount(0)
        if tbl:
            tbody = tbl.find("tbody") or tbl
            for tr in tbody.find_all("tr"):
                tds = tr.find_all(["td","th"])
                if not tds: continue
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

        row = QHBoxLayout()
        b_add = QPushButton("Add Row"); b_del = QPushButton("Remove Selected")
        b_add.clicked.connect(lambda: (self.collection_tbl.insertRow(self.collection_tbl.rowCount()), self._on_any_changed()))
        b_del.clicked.connect(lambda: (self.collection_tbl.removeRow(self.collection_tbl.currentRow()) if self.collection_tbl.currentRow()>=0 else None, self._on_any_changed()))
        row.addWidget(b_add); row.addWidget(b_del); row.addStretch(1)
        col_v.addWidget(self.collection_tbl, 1); col_v.addLayout(row)

        # Insert/replace as the "Collection" tab if needed
        idx_collection = self.tabs.indexOf(self.collection_host)
        if idx_collection == -1:
            self.tabs.addTab(self.collection_host, "Collection")

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
        self.refresh_file_icons(light=True)

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
        self.refresh_file_icons(light=True)

        # ---------- Collection save ----------
    def _save_collection_into_soup(self, soup: "BeautifulSoup"):
        """
        Persist the 'Collection' tab into the HTML:
        - Ensures <main><section> exist
        - Replaces any existing table with a fresh one
        - Columns: Part No | Title (link) | Pieces per Panel
        """
        body = soup.body or soup

        # Ensure <main> exists
        main = body.find("main")
        if not main:
            main = soup.new_tag("main")
            body.append(main)

        # Ensure a section holder for the table
        section = main.find("section")
        if not section:
            section = soup.new_tag("section")
            main.append(section)

        # Remove any previous table in section (or legacy table under main)
        old_tbl = section.find("table") or main.find("table")
        if old_tbl:
            old_tbl.decompose()

        # Build new table
        tbl = soup.new_tag("table")
        thead = soup.new_tag("thead")
        trh = soup.new_tag("tr")
        for name in ("Part No", "Title", "Pieces per Panel"):
            th = soup.new_tag("th")
            th.string = name
            trh.append(th)
        thead.append(trh)
        tbl.append(thead)

        tbody = soup.new_tag("tbody")

        # Read rows from the UI table
        def _cell_text(r: int, c: int) -> str:
            it = self.collection_tbl.item(r, c)
            return (it.text().strip() if it else "")

        rows = self.collection_tbl.rowCount() if hasattr(self, "collection_tbl") else 0
        for r in range(rows):
            part = _cell_text(r, 0)
            title_text = _cell_text(r, 1)
            href = _cell_text(r, 2)
            pieces = _cell_text(r, 3)

            # Skip totally empty rows
            if not (part or title_text or href or pieces):
                continue

            tr = soup.new_tag("tr")

            # Part No
            td_part = soup.new_tag("td")
            if part:
                td_part.string = part
            tr.append(td_part)

            # Title (as a link if href or text present)
            td_title = soup.new_tag("td")
            if title_text or href:
                a = soup.new_tag("a", href=(href or "#"))
                a.string = (title_text or href or "")
                # open external links safely
                if href and (href.startswith("http://") or href.startswith("https://")):
                    a["target"] = "_blank"
                    a["rel"] = "noopener"
                td_title.append(a)
            tr.append(td_title)

            # Pieces per Panel
            td_pieces = soup.new_tag("td")
            if pieces:
                td_pieces.string = pieces
            tr.append(td_pieces)

            tbody.append(tr)

        tbl.append(tbody)
        section.append(tbl)

    # ---------- Build soup from current UI ----------
    def _build_soup_from_ui(self, use_template: bool) -> BeautifulSoup:
        if use_template:
            html = self._template_html(self.page_mode)
            soup = BeautifulSoup(html, "html.parser")
        else:
            txt = self.current_path.read_text(encoding="utf-8")
            soup = BeautifulSoup(txt, "html.parser")
            # If the page structure doesn't match the expected mode, rebuild from template
            if (self.page_mode == "detail" and not soup.find("div", class_="tab-container")) or \
               (self.page_mode == "collection" and soup.find("div", class_="tab-container")):
                soup = BeautifulSoup(self._template_html(self.page_mode), "html.parser")

        # Metadata + Nav
        self._upsert_metadata_into_soup(soup)
        self._upsert_nav_into_soup(soup)

        if self.page_mode == "collection":
            self._save_collection_into_soup(soup)
            self._strip_detail_scripts(soup)
        else:
            self._save_detail_into_soup(soup, force_active="schematic" if use_template else None)
            self._ensure_detail_scripts(soup)

        # >>> NEW: always guarantee a footer exists and is placed last
        self._ensure_footer(soup)

        return soup

    def _strip_detail_scripts(self, soup: BeautifulSoup):
        lb = soup.find(id="lightbox")
        if lb: lb.decompose()
        for s in soup.find_all("script"): s.decompose()

    # ---------- FMEA seeds: hidden backing fields ----------
    def _ensure_fmea_seed_fields(self):
        """
        Ensure hidden QTextEdits exist for L0..L3 so that the seed builder dialog
        has a place to read/write. These are not shown in the UI (seeds are hidden).
        """
        def mk():
            te = QTextEdit()
            te.setAcceptRichText(False)
            te.setVisible(False)
            te.textChanged.connect(self._on_any_changed)
            return te

        if not hasattr(self, "ed_seed_l0"): self.ed_seed_l0 = mk()
        if not hasattr(self, "ed_seed_l1"): self.ed_seed_l1 = mk()
        if not hasattr(self, "ed_seed_l2"): self.ed_seed_l2 = mk()
        if not hasattr(self, "ed_seed_l3"): self.ed_seed_l3 = mk()

    # ---------- FMEA Seed Builder (dialog + sequential AI) ----------
    def _open_seed_builder(self):
        """
        Opens the multi-level FMEA seed builder dialog, lets the user pick sources per level,
        then sequentially composes L0→L1→L2→L3 seeds with AI. Progress is surfaced on the
        FMEA AI status label and progress bar.
        """
        # Hidden seed fields (backing storage) must exist
        self._ensure_fmea_seed_fields()

        # Gather material the dialog can use as selectable sources
        src: Dict[str, str] = {
            "Title": self.ed_title.text().strip(),
            "Slogan": self.ed_slogan.text().strip(),
            "Details": "\n".join(filter(None, [
                f"Part No: {self.det_part.text().strip()}",
                f"Board Size: {self.det_board.text().strip()}",
                f"Pieces per Panel: {self.det_pieces.text().strip()}",
                f"Panel Size: {self.det_panel.text().strip()}",
            ])),
            "Description Seed": self.desc_seed.toPlainText().strip() if hasattr(self, "desc_seed") else "",
            "Description Generated": self.desc_generated.toPlainText().strip() if hasattr(self, "desc_generated") else "",
            "Videos": "\n".join(self._table_to_list(self.sim_table)) if hasattr(self, "sim_table") else "",
            "Downloads": "\n".join([f"{t} -> {h}" for (t, h) in getattr(self, "_iter_download_rows", lambda: [])()]) if hasattr(self, "dl_table") else "",
            "Resources": "\n".join(self._table_to_list(self.res_table)) if hasattr(self, "res_table") else "",
            "Seed L1": self.ed_seed_l1.toPlainText().strip(),
            "Seed L2": self.ed_seed_l2.toPlainText().strip(),
            "Seed L3": self.ed_seed_l3.toPlainText().strip(),
        }

        # Reasonable defaults for which sources each level can consider
        defaults = {
            "Title": ["L0", "L1", "L2", "L3"],
            "Slogan": ["L0", "L1", "L2", "L3"],
            "Details": ["L0", "L1", "L2", "L3"],
            "Description Seed": ["L0", "L1", "L2"],
            "Description Generated": ["L1", "L2"],
            "Videos": ["L1", "L2"],
            "Downloads": ["L1", "L2"],
            "Resources": ["L1", "L2"],
            "Seed L1": ["L2", "L3"],  # prior seed usable by higher levels only
            "Seed L2": ["L3"],
            "Seed L3": [],             # never considered
        }

        dlg = SeedBuilderDialog(self, src, defaults)
        try:
            apply_windows_dark_titlebar(dlg)
        except Exception:
            pass
        if dlg.exec_() != QDialog.Accepted:
            return

        sel = dlg.selections()
        prompts = sel.get("prompts", {})

        # Pre-flight checks for AI
        if not OPENAI_AVAILABLE:
            self._warn("OpenAI not installed", "pip install openai")
            return
        if not self.openai_key:
            self._warn("API key required", "OpenAI API key not set.")
            return

        # Sequential build L0→L1→L2→L3
        levels = ["L0", "L1", "L2", "L3"]
        outputs: Dict[str, str] = {}

        self._start_seq_progress("Building Seeds…", total=len(levels))
        try:
            for lv in levels:
                used = sel["sources_by_level"].get(lv, [])
                bundle = []

                # Collate selected material, allowing higher levels to consider previous seeds
                for key in used:
                    if key.startswith("Seed "):
                        # Pull from outputs computed earlier in this loop
                        if key == "Seed L1" and "L1" in outputs:
                            bundle.append(f"L1 (generated):\n{outputs['L1']}")
                        if key == "Seed L2" and "L2" in outputs:
                            bundle.append(f"L2 (generated):\n{outputs['L2']}")
                        # Seed L3 is never considered
                    else:
                        txt = src.get(key, "")
                        if txt:
                            bundle.append(f"{key}:\n{txt}")

                custom_prompt = prompts.get(lv, "").strip()

                sys_prompt = (
                    "You are assisting with an FMEA planning workflow. Produce a compact, neutral SEED NOTE for the given level.\n"
                    "Keep to 120-220 words. Use plain text or minimal bullets. No HTML, no styling."
                )
                user = (
                    f"LEVEL: {lv}\n"
                    f"CUSTOM PROMPT:\n{custom_prompt}\n\n"
                    "MATERIAL TO CONSIDER:\n" + ("\n\n".join(bundle) if bundle else "(none)")
                )

                worker = BaseAIWorker(self.openai_key, self.openai_model, sys_prompt, user, timeout=120)
                res = self._run_worker_blocking(worker)
                if not res.get("ok"):
                    self._error("Seed Builder", res.get("error", "Unknown error"))
                    return

                outputs[lv] = (res.get("bundle") or "").strip()
                self._bump_seq_progress()

        finally:
            self._finish_seq_progress()

        # Persist in hidden backing fields
        self.ed_seed_l0.blockSignals(True); self.ed_seed_l0.setPlainText(outputs.get("L0", "")); self.ed_seed_l0.blockSignals(False)
        self.ed_seed_l1.blockSignals(True); self.ed_seed_l1.setPlainText(outputs.get("L1", "")); self.ed_seed_l1.blockSignals(False)
        self.ed_seed_l2.blockSignals(True); self.ed_seed_l2.setPlainText(outputs.get("L2", "")); self.ed_seed_l2.blockSignals(False)
        self.ed_seed_l3.blockSignals(True); self.ed_seed_l3.setPlainText(outputs.get("L3", "")); self.ed_seed_l3.blockSignals(False)

        # Optional: record a snapshot in the small history list if you keep it
        if hasattr(self, "_push_seed_history"):
            stamp = f"Built {today_iso()} {datetime.datetime.now().strftime('%H:%M:%S')}"
            self._push_seed_history({
                "L0": outputs.get("L0", ""),
                "L1": outputs.get("L1", ""),
                "L2": outputs.get("L2", ""),
                "L3": outputs.get("L3", ""),
            }, label=stamp)

        # Mark dirty so Save/Autosave persists into hidden JSON on next write
        self._on_any_changed()

    # ---------- Sequence progress (FMEA seeds) ----------
    def _start_seq_progress(self, title: str, total: int):
        """
        Initialize a simple progress readout on the FMEA status label and show the spinner.
        """
        self._ai_seq_total = int(max(1, total))
        self._ai_seq_done = 0
        if hasattr(self, "lbl_fmea_ai"):
            self.lbl_fmea_ai.setText(f"{title} (0/{self._ai_seq_total})")
        if hasattr(self, "pb_fmea"):
            self.pb_fmea.show()
        # keep UI responsive
        QApplication.processEvents()

    def _bump_seq_progress(self):
        """
        Bump the counter, refresh label.
        """
        self._ai_seq_done = int(getattr(self, "_ai_seq_done", 0)) + 1
        tot = int(getattr(self, "_ai_seq_total", 1))
        if hasattr(self, "lbl_fmea_ai"):
            self.lbl_fmea_ai.setText(f"Building Seeds… ({min(self._ai_seq_done, tot)}/{tot})")
        QApplication.processEvents()

    def _finish_seq_progress(self):
        """
        Conclude the sequence; hide spinner and set a friendly status.
        """
        if hasattr(self, "pb_fmea"):
            self.pb_fmea.hide()
        if hasattr(self, "lbl_fmea_ai"):
            self.lbl_fmea_ai.setText("AI: idle")
        QApplication.processEvents()

    # ---------- FMEA seed snapshots & history ----------
    def _snapshot_seeds(self):
        """
        Take a snapshot of current FMEA seeds (L0..L3) into the history list.
        Ensures hidden seed fields exist so this never crashes, even if seeds are dialog-only.
        """
        # Make sure backing fields exist
        self._ensure_fmea_seed_fields()

        snap = {
            "L0": self.ed_seed_l0.toPlainText().strip(),
            "L1": self.ed_seed_l1.toPlainText().strip(),
            "L2": self.ed_seed_l2.toPlainText().strip(),
            "L3": self.ed_seed_l3.toPlainText().strip(),
        }
        label = f"Snapshot {today_iso()} {datetime.datetime.now().strftime('%H:%M:%S')}"
        self._push_seed_history(snap, label=label)
        self._on_any_changed()

    def _push_seed_history(self, obj: Dict[str, str], label: str):
        """
        Insert a new entry into the seed history list. Creates the list widget if missing.
        `obj` should be a dict with keys L0..L3.
        """
        try:
            payload = json.dumps(obj, ensure_ascii=False)
        except Exception:
            # Fall back to a minimal structure if something went wrong
            payload = json.dumps({
                "L0": obj.get("L0", ""),
                "L1": obj.get("L1", ""),
                "L2": obj.get("L2", ""),
                "L3": obj.get("L3", ""),
            }, ensure_ascii=False)

        # Make sure the list exists; some builds may not have created it yet
        if not hasattr(self, "list_seed_history") or self.list_seed_history is None:
            self.list_seed_history = QListWidget()
            # If you want it visible, you can add it somewhere; for now it’s a safe sink.
            # Example (only if you have a layout to add to): some_layout.addWidget(self.list_seed_history)
            try:
                self.list_seed_history.itemDoubleClicked.connect(self._load_seed_history_item)
            except Exception:
                pass

        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, payload)
        # Insert at the top
        self.list_seed_history.insertItem(0, item)

    def _load_seed_history_item(self, item: QListWidgetItem):
        """
        Double-click handler to restore a snapshot back into the hidden seed fields.
        Safe even if fields are not yet created (they will be).
        """
        self._ensure_fmea_seed_fields()
        try:
            obj = json.loads(item.data(Qt.UserRole) or "{}")
        except Exception:
            obj = {}

        def set_text(widget_attr: str, key: str):
            if hasattr(self, widget_attr):
                te = getattr(self, widget_attr)
                if isinstance(te, QTextEdit):
                    te.blockSignals(True)
                    te.setPlainText(obj.get(key, ""))
                    te.blockSignals(False)

        set_text("ed_seed_l0", "L0")
        set_text("ed_seed_l1", "L1")
        set_text("ed_seed_l2", "L2")
        set_text("ed_seed_l3", "L3")

        self._on_any_changed()

    # ---------- Save Seeds → HTML (hidden JSON under #seeds tab) ----------
    def _save_seeds_to_html(self):
        """
        Persist the current seed fields to the HTML file:
          - Description seed -> <script id="ai-seed-description" type="application/json">…</script>
          - DTP / ATP seeds -> <script id="ai-seed-dtp|ai-seed-atp" type="application/json">…</script>
          - FMEA L0-L3     -> <script id="ai-seeds-fmea" type="application/json">{"L0":..., ...}</script>
        These are written inside a hidden 'seeds' tab-content div (data-hidden="true") and the tab
        is never listed in the tab header.
        """
        # Basic guards
        if not self.current_path or not self.current_path.exists():
            self._warn("Save Seeds", "Open a detail page first."); 
            return
        if not BS4_AVAILABLE:
            self._warn("BeautifulSoup required", "pip install beautifulsoup4")
            return

        # Only makes sense for detail pages, since collection pages don't host seeds
        if getattr(self, "page_mode", "detail") != "detail":
            self._warn("Save Seeds", "Seeds can only be saved on a board/detail page.")
            return

        try:
            # Build soup from current UI state; this will call _save_detail_into_soup(...)
            soup = self._build_soup_from_ui(use_template=False)

            # Format and write safely (atomic replace)
            out_txt = minipcb_format_html(soup)
            tmp = self.current_path.with_suffix(self.current_path.suffix + f".seeds.{os.getpid()}.{now_stamp()}")
            tmp.write_text(out_txt, encoding="utf-8")
            os.replace(str(tmp), str(self.current_path))

            # Refresh UI stats, clear dirty flag, and nudge icons
            self._set_stats(self.current_path)
            self._set_dirty(False)
            self.refresh_file_icons(light=True)

            # Notify
            self._info("Seeds Saved", "All seeds (Description, DTP, ATP, FMEA L0-L3) saved as hidden JSON in the HTML.")
        except Exception as e:
            try:
                if 'tmp' in locals() and tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            self._error("Save error", f"Failed to save seeds:\n{e}")

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

    def _ensure_hidden_seeds_section(self, soup: BeautifulSoup):
        """Create <div class='tab-content' id='ai-seeds' data-hidden='true'> with seeds JSON scripts inside."""
        tabc, _ = self._ensure_container_and_tabs_div(soup)
        div = tabc.find("div", class_="tab-content", id="ai-seeds")
        if not div:
            div = soup.new_tag("div", **{"class":"tab-content", "id":"ai-seeds", "data-hidden":"true"})
            # no <h2>, keep fully hidden/no heading
            tabc.append(div)
        else:
            div["data-hidden"] = "true"
        return div

    def _mark_section_hidden(self, soup: BeautifulSoup, sec_id: str, hidden: bool):
        div = soup.find("div", class_="tab-content", id=sec_id)
        if not div: return
        if hidden: div["data-hidden"] = "true"
        else: div.attrs.pop("data-hidden", None)

    def _rebuild_tabs_header(self, soup: "BeautifulSoup", force_active: Optional[str] = None):
        tabc, tabs = self._ensure_container_and_tabs_div(soup)
        enabled = {
            "details": True,
            "description": self.chk_desc.isChecked(),
            "simulation": self.chk_videos.isChecked(),
            "schematic": True,
            "layout": True,
            "downloads": self.chk_downloads.isChecked(),
            "resources": self.chk_resources.isChecked(),
            "fmea": self.chk_fmea.isChecked(),
            # "seeds": False  # NEVER listed
        }
        order = [("details","Details"), ("description","Description"), ("simulation","Videos"),
                 ("schematic","Schematic"), ("layout","Layout"), ("downloads","Downloads"),
                 ("resources","Additional Resources"), ("fmea","FMEA")]

        active_div = tabc.find("div", class_="tab-content", id=re.compile(r".*"), attrs={"class":re.compile(r"\bactive\b")})
        active_id = force_active or (active_div.get("id") if active_div else "schematic")
        if active_id not in enabled or not enabled.get(active_id, False):
            active_id = "schematic"

        # Rebuild buttons
        for ch in list(tabs.children):
            if isinstance(ch, Tag): ch.decompose()
        for sec_id, label in order:
            if not enabled.get(sec_id, False): continue
            btn = soup.new_tag("button", **{"class":"tab" + (" active" if sec_id==active_id else ""), "onclick":f"showTab('{sec_id}', this)"})
            btn.string = label; tabs.append(btn)

        # Apply 'active' class across panes
        for div in tabc.find_all("div", class_="tab-content"):
            classes = (div.get("class") or [])
            if "tab-content" not in classes: continue
            if div.get("id") == active_id:
                if "active" not in classes: classes.append("active")
            else:
                classes = [c for c in classes if c != "active"]
            div["class"] = classes

    def _save_detail_into_soup(self, soup: "BeautifulSoup", force_active: Optional[str] = None):
        # ----- Details -----
        det_div = self._ensure_section(soup, "details", "Details")
        for node in list(det_div.find_all(recursive=False))[1:]: node.decompose()

        def mk_detail(label: str, value: str):
            p = soup.new_tag("p"); strong = soup.new_tag("strong"); strong.string = f"{label}:"
            p.append(strong); p.append(" " + value); return p

        det_div.append(mk_detail("Part No", self.det_part.text().strip()))
        det_div.append(mk_detail("Title", self.det_title.text().strip()))
        det_div.append(mk_detail("Board Size", self.det_board.text().strip()))
        det_div.append(mk_detail("Pieces per Panel", self.det_pieces.text().strip()))
        det_div.append(mk_detail("Panel Size", self.det_panel.text().strip()))

        # ----- Description (no visible seed; seed is hidden in 'seeds' tab/json) -----
        dsc_div = self._ensure_section(soup, "description", "Description")
        for node in list(dsc_div.find_all(recursive=False))[1:]: node.decompose()

        h3g = soup.new_tag("h3"); h3g.string = "AI Generated"; dsc_div.append(h3g)
        wrap = soup.new_tag("div", **{"class":"generated"})
        frag = self.desc_generated.toHtml()
        clean_nodes = self._sanitize_ai_fragment(frag, soup)
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
            a = soup.new_tag("a", href=href or "#")
            a.string = text or href or "Download"
            if href and (href.startswith("http://") or href.startswith("https://")):
                a["target"] = "_blank"; a["rel"] = "noopener"
            li = soup.new_tag("li"); li.append(a); ul.append(li)
        dl_div.append(ul)

        # ----- Resources -----
        res_div = self._ensure_section(soup, "resources", "Additional Resources")
        for node in list(res_div.find_all(recursive=False))[1:]: node.decompose()
        self._write_iframe_list(soup, res_div, self._table_to_list(self.res_table))

        # ----- FMEA (table only; seeds are hidden) -----
        fmea_div = self._ensure_section(soup, "fmea", "FMEA")
        for node in list(fmea_div.find_all(recursive=False))[1:]: node.decompose()
        frag_html = self.fmea_html.toHtml().strip()
        if frag_html:
            try:
                frag = BeautifulSoup(frag_html, "html.parser")
                tbl = frag.find("table")
                if tbl:
                    tbl["class"] = (tbl.get("class", []) + ["fmea-table"])
                    for tag in tbl.find_all(True): tag.attrs.pop("style", None)
                    fmea_div.append(tbl)
            except Exception:
                pass

        # ----- Hidden seeds (not-listed tab) -----
        # Create/ensure a "seeds" tab-content that is never listed in header and always hidden.
        seeds_div = self._ensure_section(soup, "seeds", "AI Seeds")
        # make sure it never shows
        seeds_div["data-hidden"] = "true"
        # Clear after heading
        for node in list(seeds_div.find_all(recursive=False))[1:]: node.decompose()

        # Store all seeds as JSON <script> tags (hidden)
        def upsert_json_script(parent: "Tag", sid: str, payload: dict | str):
            tag = seeds_div.find("script", id=sid, attrs={"type":"application/json"})
            if not tag:
                tag = soup.new_tag("script", id=sid, type="application/json")
                tag["data-hidden"] = "true"
                parent.append(tag)
            tag.string = json.dumps(payload, ensure_ascii=False, indent=0) if isinstance(payload, dict) else (payload or "")

        # Description seed (single string)
        upsert_json_script(seeds_div, "ai-seed-description", self.desc_seed.toPlainText().strip())
        # Testing seeds (strings)
        upsert_json_script(seeds_div, "ai-seed-dtp", self.dtp_seed.toPlainText().strip() if hasattr(self, "dtp_seed") else "")
        upsert_json_script(seeds_div, "ai-seed-atp", self.atp_seed.toPlainText().strip() if hasattr(self, "atp_seed") else "")
        # FMEA seeds (object)
        fmea_payload = {
            "L0": self.ed_seed_l0.toPlainText().strip() if hasattr(self, "ed_seed_l0") else "",
            "L1": self.ed_seed_l1.toPlainText().strip() if hasattr(self, "ed_seed_l1") else "",
            "L2": self.ed_seed_l2.toPlainText().strip() if hasattr(self, "ed_seed_l2") else "",
            "L3": self.ed_seed_l3.toPlainText().strip() if hasattr(self, "ed_seed_l3") else "",
        }
        upsert_json_script(seeds_div, "ai-seeds-fmea", fmea_payload)

        # ----- Component visibility flags -----
        self._mark_section_hidden(soup, "description", not self.chk_desc.isChecked())
        self._mark_section_hidden(soup, "simulation", not self.chk_videos.isChecked())
        self._mark_section_hidden(soup, "downloads", not self.chk_downloads.isChecked())
        self._mark_section_hidden(soup, "resources", not self.chk_resources.isChecked())
        self._mark_section_hidden(soup, "fmea", not self.chk_fmea.isChecked())
        # seeds tab always hidden; never listed

        # ----- Rebuild tabs (do not include seeds tab in header) -----
        self._rebuild_tabs_header(soup, force_active=force_active)

    # ---------- Hidden seeds handling ----------
    def _upsert_all_seeds_hidden_json(self, soup: BeautifulSoup):
        div = self._ensure_hidden_seeds_section(soup)
        # remove previous scripts inside the hidden section
        for ch in list(div.children):
            if isinstance(ch, Tag) and ch.name == "script" and ch.get("type") == "application/json":
                ch.decompose()

        payload = {
            "description_seed": self._seed_desc or "",
            "fmea": {
                "L0": self._seeds_fmea.get("L0",""),
                "L1": self._seeds_fmea.get("L1",""),
                "L2": self._seeds_fmea.get("L2",""),
                "L3": self._seeds_fmea.get("L3",""),
            },
            "testing": {
                "dtp_seed": self._seed_dtp or self.dtp_seed.toPlainText().strip(),
                "atp_seed": self._seed_atp or self.atp_seed.toPlainText().strip(),
            }
        }
        tag = soup.new_tag("script", id="ai-seeds-json", type="application/json")
        tag.string = json.dumps(payload, ensure_ascii=False, separators=(",",":"))
        div.append(tag)

    def _load_hidden_seeds_from_soup(self, soup: BeautifulSoup):
        tag = soup.find("script", id="ai-seeds-json", attrs={"type":"application/json"})
        if not tag or not (tag.string or "").strip(): return
        try:
            obj = json.loads(tag.string)
            self._seed_desc = obj.get("description_seed","") or ""
            f = obj.get("fmea",{}) or {}
            self._seeds_fmea = {
                "L0": f.get("L0","") or "",
                "L1": f.get("L1","") or "",
                "L2": f.get("L2","") or "",
                "L3": f.get("L3","") or "",
            }
            t = obj.get("testing",{}) or {}
            self._seed_dtp = t.get("dtp_seed","") or ""
            self._seed_atp = t.get("atp_seed","") or ""
        except Exception:
            pass

    def _save_fmea_seeds_from_dialog(self, seeds: Dict[str,str]):
        self._seeds_fmea = dict(seeds or {})
        self._save_seeds_hidden_to_html()

    def _save_description_seed_from_dialog(self, seed_text: str):
        self._seed_desc = seed_text or ""
        self._save_seeds_hidden_to_html()

    def _save_seeds_hidden_to_html(self):
        if not self.current_path or not self.current_path.exists() or not BS4_AVAILABLE:
            self._warn("Save Seeds", "Open a detail page first."); return
        soup = self._build_soup_from_ui(use_template=False)
        out_txt = minipcb_format_html(soup)
        try:
            self.current_path.write_text(out_txt, encoding="utf-8")
            self._set_stats(self.current_path); self._set_dirty(False)
            self._info("Seeds Saved", "All seeds saved to hidden JSON inside a hidden tab.")
        except Exception as e:
            self._error("Save error", str(e))

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
        mb.setIcon(QMessageBox.Question); mb.setStandardButtons(QMessageBox.Yes | QDialogButtonBox.No)
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
            pidx = self.proxy.mapFromSource(sidx)
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

    # ---------- Dialog openers ----------
    def _open_fmea_seeds_dialog(self):
        def _gather_sources():
            src: Dict[str,str] = {
                "Title": self.ed_title.text().strip(),
                "Slogan": self.ed_slogan.text().strip(),
                "Details": "\n".join(filter(None, [
                    f"Part No: {self.det_part.text().strip()}",
                    f"Board Size: {self.det_board.text().strip()}",
                    f"Pieces per Panel: {self.det_pieces.text().strip()}",
                    f"Panel Size: {self.det_panel.text().strip()}",
                ])),
                "Description Seed": self._seed_desc,
                "Description Generated": self.desc_generated.toPlainText().strip() if hasattr(self.desc_generated, "toPlainText") else "",
                "Videos": "\n".join(self._table_to_list(self.sim_table)),
                "Downloads": "\n".join([f"{t} -> {h}" for (t,h) in self._iter_download_rows()]),
                "Resources": "\n".join(self._table_to_list(self.res_table)),
                "Seed L1": self._seeds_fmea.get("L1",""),
                "Seed L2": self._seeds_fmea.get("L2",""),
                "Seed L3": self._seeds_fmea.get("L3",""),
            }
            defaults = {
                "Title": ["L0","L1","L2","L3"],
                "Slogan": ["L0","L1","L2","L3"],
                "Details": ["L0","L1","L2","L3"],
                "Description Seed": ["L0","L1","L2"],
                "Description Generated": ["L1","L2"],
                "Videos": ["L1","L2"],
                "Downloads": ["L1","L2"],
                "Resources": ["L1","L2"],
                "Seed L1": ["L2","L3"],
                "Seed L2": ["L3"],
                "Seed L3": [],
            }
            return src, defaults

        dlg = FMEASeedsDialog(self, dict(self._seeds_fmea), _gather_sources)
        apply_windows_dark_titlebar(dlg)
        dlg.exec_()
        self._seeds_fmea = dlg.value()
        self._on_any_changed()

    # ---------- Description Seed editor (dialog) ----------
    def _open_desc_seed_dialog(self):
        """
        Open a modal dialog to edit the Description seed.
        When opening, auto-switch the section editor to the Schematic tab so the user sees the schematic image.
        On close, restore the previous section tab.
        """
        prev_index = self.sections_tabs.currentIndex()

        # Show Schematic tab first (for visual context while typing)
        try:
            schem_idx = self.sections_tabs.indexOf(self.w_schematic)
            if schem_idx != -1:
                self.sections_tabs.setCurrentIndex(schem_idx)
                QApplication.processEvents()
        except Exception:
            pass

        # Build dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Description Seed")
        dlg.resize(780, 560)
        v = QVBoxLayout(dlg)

        info = QLabel("Enter seed notes for the Description generator. Plain text only.")
        info.setWordWrap(True)
        v.addWidget(info)

        ed = QTextEdit()
        ed.setAcceptRichText(False)
        ed.setPlainText(self.desc_seed.toPlainText().strip())
        ed.setMinimumHeight(400)
        v.addWidget(ed, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, dlg)
        v.addWidget(btns)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        try:
            apply_windows_dark_titlebar(dlg)
        except Exception:
            pass

        if dlg.exec_() == QDialog.Accepted:
            self.desc_seed.blockSignals(True)
            self.desc_seed.setPlainText(ed.toPlainText().strip())
            self.desc_seed.blockSignals(False)
            self._on_any_changed()

        # Restore previously selected section
        try:
            if 0 <= prev_index < self.sections_tabs.count():
                self.sections_tabs.setCurrentIndex(prev_index)
        except Exception:
            pass

    # ---------- Block-until AI helper (for builder) ----------
    def _run_worker_blocking(self, worker: BaseAIWorker) -> dict:
        data = {}
        def _on_done(res): data.update(res)
        worker.finished.connect(_on_done)
        worker.start()
        while worker.isRunning():
            QApplication.processEvents()
            time.sleep(0.05)
        return data

    # ---------- AI (Description) ----------
    def _start_desc_ai(self):
        if self._ai_running: return
        if not OPENAI_AVAILABLE:
            self._warn("OpenAI not installed", "pip install openai"); return
        if not self.openai_key:
            self._warn("API key required", "OpenAI API key not set."); return
        page_title = self.ed_title.text().strip(); h1 = self.ed_h1.text().strip(); part_no = self.det_part.text().strip()
        seed = self._seed_desc or ""
        sys_prompt = ("You are an expert technical copywriter for a hardware mini PCB catalog.\n"
                      "Write crisp, accurate, helpful product descriptions. Return ONLY an HTML fragment (p/ul/li/h3 ok), no inline styles.")
        user = (
            f"PAGE CONTEXT:\n- Page Title: {page_title}\n- H1: {h1}\n- Part No: {part_no}\n\n"
            f"SEED:\n{seed}\n\n"
            "TASK:\n• 2-4 short paragraphs + (optional) one bullet list (3-6 items).\n"
            "• 180-260 words; neutral, technical; no marketing fluff.\n"
            "• Output ONLY an HTML fragment; no <html>/<body>; no inline styles."
        )
        self._kick_ai(sys_prompt, user, target="desc")

    # ---------- AI (FMEA) ----------
    def _start_fmea_ai(self):
        if self._ai_running: return
        if not OPENAI_AVAILABLE:
            self._warn("OpenAI not installed", "pip install openai"); return
        if not self.openai_key:
            self._warn("API key required", "OpenAI API key not set."); return

        seeds = dict(self._seeds_fmea)
        details = {
            "Part No": self.det_part.text().strip(),
            "Title": self.det_title.text().strip(),
            "Board Size": self.det_board.text().strip(),
            "Pieces per Panel": self.det_pieces.text().strip(),
            "Panel Size": self.det_panel.text().strip(),
        }
        pagectx = f"PAGE: title={self.ed_title.text().strip()} h1={self.ed_h1.text().strip()} part_no={details['Part No']}"
        sys_prompt = (
            "You are an expert test engineer. Generate a compact HTML <table> (no inline styles) for an FMEA.\n"
            "Headers: ID | Item | Failure Mode | Effect | Detection (TP#…) | Test ID | Severity | Occurrence | Detectability | RPN.\n"
            "Use concise sentences; numeric S/O/D 1-10; compute RPN = S*O*D. No extra text around the table."
        )
        user = (
            f"{pagectx}\nDETAILS:\n{json.dumps(details, ensure_ascii=False)}\n"
            f"L0:\n{seeds.get('L0','')}\n\nL1:\n{seeds.get('L1','')}\n\nL2:\n{seeds.get('L2','')}\n\nFINAL L3:\n{seeds.get('L3','')}\n\n"
            "TASK:\nReturn ONLY a single <table> element with the specified header. Use class=\"fmea-table\"."
        )
        self._kick_ai(sys_prompt, user, target="fmea")

    # ---------- AI (Testing: DTP/ATP) ----------
    def _start_test_ai(self, kind: str):
        if self._ai_running: return
        if not OPENAI_AVAILABLE:
            self._warn("OpenAI not installed", "pip install openai"); return
        if not self.openai_key:
            self._warn("API key required", "OpenAI API key not set."); return

        details = {
            "Part No": self.det_part.text().strip(),
            "Title": self.det_title.text().strip(),
            "Board Size": self.det_board.text().strip(),
            "Pieces per Panel": self.det_pieces.text().strip(),
            "Panel Size": self.det_panel.text().strip(),
        }
        seed_text = (self.dtp_seed.toPlainText().strip() if kind=="dtp" else self.atp_seed.toPlainText().strip())
        # store to in-memory seeds so Save→HTML persists them in hidden JSON
        if kind == "dtp": self._seed_dtp = seed_text
        else: self._seed_atp = seed_text

        sys_prompt = (
            "You are a hardware test engineer. Produce a concise Markdown checklist of tests.\n"
            "- Each test as a bullet: **Test ID** - short name: 1-line purpose; Steps: 2-5 compact steps; Expected: one line.\n"
            "- Keep it crisp and hardware-focused; avoid tables and code unless essential.\n"
            f"Context: Generate a {'Developmental' if kind=='dtp' else 'Production-Automated'} Test Plan."
        )
        user = (
            f"DETAILS:\n{json.dumps(details, ensure_ascii=False)}\n\n"
            f"SEED/NOTES:\n{seed_text}\n\n"
            "Return ONLY the Markdown bullet list."
        )
        self._kick_ai(sys_prompt, user, target=f"test-{kind}")

    # ---------- AI orchestration (shared) ----------
    def _kick_ai(self, sys_prompt: str, user_prompt: str, target: str):
        self._ai_running = True; self._ai_start_ts = datetime.datetime.now(); self._ai_eta_sec = 75; self._ai_target = target

        # show progress where appropriate
        if target == "desc":
            self.lbl_desc_ai.setText("AI: starting…"); self.pb_desc.show()
        elif target == "fmea":
            self.lbl_fmea_ai.setText("AI: starting…"); self.pb_fmea.show()
        elif target == "test-dtp":
            self.lbl_dtp_ai.setText("AI: starting…"); self.pb_dtp.show()
        elif target == "test-atp":
            self.lbl_atp_ai.setText("AI: starting…"); self.pb_atp.show()

        self.ai_timer.start(250)
        self._worker = BaseAIWorker(self.openai_key, self.openai_model, sys_prompt, user_prompt, timeout=240)
        self._worker.finished.connect(lambda res, tgt=target: self._on_ai_finished(res, tgt))
        self._worker.start()

    def _on_ai_finished(self, result: dict, target: str):
        elapsed = int(result.get("elapsed", 0))
        # keep ETA display consistent
        self._update_ai_label(elapsed=elapsed, eta=self._ai_eta_sec, target=target if target in ("desc","fmea","dtp","atp") else "both", status="done")
        self.ai_timer.stop(); self._ai_running = False

        # Hide relevant spinners
        if target == "desc": self.pb_desc.hide()
        if target == "fmea": self.pb_fmea.hide()
        if target == "dtp":  self.pb_dtp.hide()
        if target == "atp":  self.pb_atp.hide()

        if not result.get("ok", False):
            self._error("AI Error", result.get("error","Unknown error")); return

        html = (result.get("bundle","") or "").strip()

        if target == "desc":
            clean_nodes = self._sanitize_ai_fragment(html, BeautifulSoup("<div></div>", "html.parser"))
            frag_html = "".join(str(n) for n in clean_nodes)
            self.desc_generated.setHtml(frag_html); self._on_any_changed()

        elif target == "fmea":
            try:
                frag = BeautifulSoup(html, "html.parser"); tbl = frag.find("table")
                if tbl:
                    for tag in tbl.find_all(True): tag.attrs.pop("style", None)
                    tbl["class"] = (tbl.get("class", []) + ["fmea-table"])
                    self.fmea_html.setHtml(str(tbl)); self._on_any_changed()
                else:
                    # sanitize generic fragment
                    clean_nodes = self._sanitize_ai_fragment(html, BeautifulSoup("<div></div>", "html.parser"))
                    self.fmea_html.setHtml("".join(str(n) for n in clean_nodes)); self._on_any_changed()
            except Exception:
                self.fmea_html.setHtml(html); self._on_any_changed()

        elif target == "dtp":
            clean_nodes = self._sanitize_ai_fragment(html, BeautifulSoup("<div></div>", "html.parser"))
            self.dtp_generated.setHtml("".join(str(n) for n in clean_nodes)); self._on_any_changed()

        elif target == "atp":
            clean_nodes = self._sanitize_ai_fragment(html, BeautifulSoup("<div></div>", "html.parser"))
            self.atp_generated.setHtml("".join(str(n) for n in clean_nodes)); self._on_any_changed()

    # ---------- Footer ----------
    def _ensure_footer(self, soup: "BeautifulSoup"):
        """
        Guarantee there is exactly one <footer> at the end of <body>.
        If absent, create a default one: © <year> miniPCB. All rights reserved.
        If present, keep existing markup but normalize basic text if empty.
        """
        year = datetime.date.today().year
        body = soup.body or soup

        # Find existing footers (some legacy files may have multiple)
        footers = body.find_all("footer") if body else []
        if not footers:
            # Create a default footer
            f = soup.new_tag("footer")
            f.string = f"© {year} miniPCB. All rights reserved."
            if body:
                body.append(f)
            else:
                soup.append(f)
            return

        # Keep the first footer; remove any extras (defensive clean-up)
        first = footers[0]
        for extra in footers[1:]:
            extra.decompose()

        # If the only footer is empty, give it a sensible default
        txt = (first.get_text(strip=True) or "")
        if not txt:
            first.clear()
            first.string = f"© {year} miniPCB. All rights reserved."

        # Ensure footer is the last element in <body> (after main content/lightbox/scripts)
        if body and first is not body.contents[-1]:
            first.extract()
            body.append(first)

    def _set_ai_status_idle_all(self):
        self._ai_running = False; self._ai_start_ts = None; self._ai_eta_sec = None; self.ai_timer.stop()

        # Description
        self.lbl_desc_ai.setText("AI: idle"); self.btn_desc_generate.setEnabled(True); self.pb_desc.hide()
        # FMEA
        self.lbl_fmea_ai.setText("AI: idle"); self.btn_fmea_generate.setEnabled(True); self.pb_fmea.hide()
        # DTP
        if hasattr(self, "lbl_dtp_ai"): self.lbl_dtp_ai.setText("AI: idle")
        if hasattr(self, "pb_dtp"): self.pb_dtp.hide()
        # ATP
        if hasattr(self, "lbl_atp_ai"): self.lbl_atp_ai.setText("AI: idle")
        if hasattr(self, "pb_atp"): self.pb_atp.hide()

    def _tick_ai_ui(self):
        if not self._ai_running or not self._ai_start_ts: return
        elapsed = int((datetime.datetime.now() - self._ai_start_ts).total_seconds())
        self._update_ai_label(elapsed=elapsed, eta=self._ai_eta_sec, target="both", status="running")

    def _update_ai_label(self, elapsed: int, eta: Optional[int], target: str, status: str):
        def fmt(sec: Optional[int]) -> str:
            if sec is None: return "--:--"
            m, s = divmod(max(0, int(sec)), 60); return f"{m:02d}:{s:02d}"
        msg = f"AI: {fmt(elapsed)} / ETA ≈ {fmt(eta)}"

        # target can be 'desc', 'fmea', 'dtp', 'atp', or 'both' (broadcast)
        if target in ("desc","both") and hasattr(self, "lbl_desc_ai"):
            self.lbl_desc_ai.setText(msg)
        if target in ("fmea","both") and hasattr(self, "lbl_fmea_ai"):
            self.lbl_fmea_ai.setText(msg)
        if target in ("dtp","both") and hasattr(self, "lbl_dtp_ai"):
            self.lbl_dtp_ai.setText(msg)
        if target in ("atp","both") and hasattr(self, "lbl_atp_ai"):
            self.lbl_atp_ai.setText(msg)

    # ---------- Sequence progress (used by FMEA Seed Builder) ----------
    def _start_seq_progress(self, title: str, total: int):
        # temporarily reuse FMEA label/pb as a sequence indicator
        self._seq_prev_running = getattr(self, "_ai_running", False)
        self._seq_prev_eta = getattr(self, "_ai_eta_sec", None)
        self._seq_prev_label = self.lbl_fmea_ai.text()
        self._seq_prev_pb_max = self.pb_fmea.maximum()
        self._seq_prev_pb_vis = self.pb_fmea.isVisible()

        self._seq_title = title or "Working…"
        self._seq_total = max(1, int(total or 1))
        self._ai_running = True
        self._ai_start_ts = datetime.datetime.now()
        self._ai_eta_sec = None
        self._ai_target = "fmea"
        self._ai_seq_progress = 0

        self.pb_fmea.setMaximum(self._seq_total)
        self.pb_fmea.setValue(0)
        self.pb_fmea.show()
        self.lbl_fmea_ai.setText(f"{self._seq_title} (0/{self._seq_total})")
        self.ai_timer.start(250)

    def _bump_seq_progress(self, step: int = 1):
        try:
            self._ai_seq_progress = min(self._seq_total, self._ai_seq_progress + int(step))
        except Exception:
            self._ai_seq_progress = getattr(self, "_ai_seq_progress", 0) + int(step or 1)
        self.pb_fmea.setValue(self._ai_seq_progress)
        self.lbl_fmea_ai.setText(f"{self._seq_title} ({self._ai_seq_progress}/{self._seq_total})")
        QApplication.processEvents()

    def _finish_seq_progress(self):
        self.lbl_fmea_ai.setText(f"{self._seq_title} — done")
        QApplication.processEvents()
        self.pb_fmea.setMaximum(self._seq_prev_pb_max if hasattr(self, "_seq_prev_pb_max") else 0)
        if not getattr(self, "_seq_prev_pb_vis", False):
            self.pb_fmea.hide()
        self._ai_running = bool(getattr(self, "_seq_prev_running", False))
        self._ai_eta_sec = getattr(self, "_seq_prev_eta", None)
        if hasattr(self, "_seq_prev_label"):
            self.lbl_fmea_ai.setText(self._seq_prev_label)
        if not self._ai_running:
            self.ai_timer.stop()
        self._ai_target = None

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

    # ---------- File icon refresh ----------
    def _get_expanded_paths(self) -> list:
        paths = []
        def walk(idx):
            if not idx.isValid(): return
            if self.tree.isExpanded(idx):
                sidx = self.proxy.mapToSource(idx)
                try:
                    p = Path(self.fs_model.filePath(sidx))
                    if p.exists(): paths.append(str(p.resolve()))
                except Exception: pass
            rows = self.proxy.rowCount(idx)
            for r in range(rows): walk(self.proxy.index(r, 0, idx))
        walk(self.tree.rootIndex()); return paths

    def _restore_expanded_paths(self, paths: list):
        for p in paths or []:
            sidx = self.fs_model.index(p)
            if sidx.isValid():
                pidx = self.proxy.mapFromSource(sidx)
                self.tree.setExpanded(pidx, True)

    def _rebuild_fs_model(self):
        sel = self.selected_path(); expanded = self._get_expanded_paths()
        self.tree.setModel(None)
        self.fs_model = QFileSystemModel(self); self.fs_model.setReadOnly(False)
        self.fs_model.setRootPath(str(self.content_root))
        self.fs_model.setNameFilters(["*.html", "*.htm"]); self.fs_model.setNameFilterDisables(False)
        self.proxy.setSourceModel(self.fs_model)
        self.tree.setModel(self.proxy)
        self.tree.setRootIndex(self.proxy.mapFromSource(self.fs_model.index(str(self.content_root))))
        self.tree.setSortingEnabled(True); self.tree.sortByColumn(0, Qt.AscendingOrder)
        self._restore_expanded_paths(expanded)
        if sel and sel.exists():
            sidx = self.fs_model.index(str(sel))
            if sidx.isValid():
                pidx = self.proxy.mapFromSource(sidx)
                self.tree.setCurrentIndex(pidx)

    def _emit_data_changed_visible(self):
        root = self.tree.rootIndex()
        def emit_for(idx):
            if not idx.isValid(): return
            sidx = self.proxy.mapToSource(idx)
            try:
                self.fs_model.dataChanged.emit(sidx, sidx)
            except Exception: pass
            rows = self.proxy.rowCount(idx)
            for r in range(rows): emit_for(self.proxy.index(r, 0, idx))
        emit_for(root)

    def _nudge_shell_icon_cache(self, path: Optional[Path]):
        if platform.system() != "Windows" or not path: return
        try:
            import ctypes
            from ctypes import wintypes
            SHCNE_UPDATEITEM = 0x00002000
            SHCNF_PATHW = 0x00000005
            ctypes.windll.shell32.SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW, wintypes.LPCWSTR(str(path)), None)
        except Exception:
            pass

    def refresh_file_icons(self, light: bool = True):
        base = self.selected_path() or self.content_root
        self._nudge_shell_icon_cache(base if isinstance(base, Path) else None)
        if light: self._emit_data_changed_visible()
        else: self._rebuild_fs_model()

    # ---------- HTML fragment sanitizer (AI output) ----------
    def _sanitize_ai_fragment(self, html_fragment: str, dest_soup: "BeautifulSoup"):
        """
        Accepts HTML from QTextEdit.toHtml() or a model (may contain a full document/DOCTYPE).
        Returns a list of sanitized nodes that BELONG to dest_soup, safe to append.
        - Strips Doctype, <script>, <style>, comments, event handlers, and inline styles.
        - Allows a minimal semantic subset: p, ul/ol/li, strong/em/b/i/u, h3/h4/h5, code/pre, br, a (limited attrs).
        - Filters suspicious/invalid <a href>.
        - Collapses stray 'HTML PUBLIC ...' lines sometimes emitted as text by rich text.
        """

        # Parse in a local soup (handles both fragments and full docs).
        try:
            local = BeautifulSoup(html_fragment or "", "html.parser")
        except Exception:
            local = BeautifulSoup("", "html.parser")

        # Prefer the body if present; otherwise use the root
        root = local.body or local

        # Remove explicit Doctype nodes anywhere in the tree
        for n in list(local.contents):
            # Older bs4 surfaces Doctype at top-level only; be defensive:
            if Doctype is not None and isinstance(n, Doctype):
                n.extract()

        # Remove script/style and comments throughout
        for bad in root.find_all(["script", "style"]):
            bad.decompose()
        for c in root.find_all(string=lambda s: isinstance(s, Comment)):
            c.extract()

        # Allowed tag -> allowed attributes
        allowed: dict[str, set[str]] = {
            "p": set(), "ul": set(), "ol": set(), "li": set(),
            "strong": set(), "em": set(), "b": set(), "i": set(), "u": set(),
            "h3": set(), "h4": set(), "h5": set(),
            "code": set(), "pre": set(), "br": set(),
            "a": {"href", "title"},
            "span": {"class"},  # minimal
        }

        def is_allowed_href(href: str) -> bool:
            if not href: return False
            href = href.strip().lower()
            return href.startswith("http://") or href.startswith("https://") or href.startswith("mailto:")

        def collapse_text(s: str) -> str:
            # strip zero-width and collapse whitespace
            s = re.sub(r"[\u200B-\u200D\uFEFF]", "", s or "")
            s = re.sub(r"[ \t\r\n]+", " ", s)
            return s.strip()

        # Heuristic for bogus DTD text blobs that sometimes come through as NavigableString
        def looks_like_doctype_text(s: str) -> bool:
            if not s: return False
            t = s.strip()
            return t.upper().startswith("HTML PUBLIC ") or t.startswith("<!DOCTYPE") or "W3C//DTD" in t

        def clean_node(node):
            """Return a list of sanitized nodes (Tags or NavigableStrings) belonging to dest_soup."""
            out = []

            # Drop Doctype if it still appears (defensive)
            if Doctype is not None and isinstance(node, Doctype):
                return out

            # Text nodes
            if isinstance(node, NavigableString) and not isinstance(node, Tag):
                txt = str(node)
                if looks_like_doctype_text(txt):
                    return out  # skip bogus DTD text
                txt = collapse_text(txt)
                if not txt:
                    return out
                out.append(dest_soup.new_string(txt))
                return out

            # Non-tags: ignore
            if not isinstance(node, Tag):
                return out

            name = (node.name or "").lower()
            # If not allowed, unwrap by cleaning and returning its children
            if name not in allowed:
                for ch in node.contents or []:
                    out.extend(clean_node(ch))
                return out

            # Create a new tag in the destination soup
            new_tag = dest_soup.new_tag(name)

            # Copy only allowed attributes and strip event handlers/inline styles
            keep = allowed[name]
            for attr, val in list(node.attrs.items()):
                if attr.lower().startswith("on"):   # onclick, onerror, etc.
                    continue
                if attr.lower() == "style":
                    continue
                if attr in keep:
                    new_tag[attr] = val

            # Special handling for <a>
            if name == "a":
                href = new_tag.get("href", "")
                if not is_allowed_href(href):
                    # invalid or empty: drop link nature, keep text only
                    new_tag.attrs.pop("href", None)
                else:
                    # enforce safe behavior
                    new_tag["target"] = "_blank"
                    new_tag["rel"] = "noopener"

            # Recurse into children
            for ch in node.contents or []:
                cleaned_children = clean_node(ch)
                for cc in cleaned_children:
                    new_tag.append(cc)

            # Drop empty tags that have no text and no meaningful children
            if not new_tag.contents or all(
                (isinstance(c, NavigableString) and not str(c).strip()) for c in new_tag.contents
            ):
                return out

            out.append(new_tag)
            return out

        # Sanitize each top-level child of the chosen root (body or local)
        sanitized_nodes = []
        for child in list(root.contents):
            sanitized_nodes.extend(clean_node(child))

        return sanitized_nodes

    # ---------- Writer for iframe/video lists ----------
    def _write_iframe_list(self, soup: "BeautifulSoup", container_div: "Tag", urls: list):
        """
        Given a list of video URLs, add a simple grid of <iframe> embeds into container_div.
        Converts common YouTube forms to embed URLs. Leaves unknown hosts as-is.
        """
        # Clear existing content after heading
        for node in list(container_div.find_all(recursive=False))[1:]:
            node.decompose()

        if not urls:
            # keep the section empty but valid
            return

        grid = soup.new_tag("div", **{"class": "video-grid"})
        container_div.append(grid)

        def to_embed(u: str) -> str:
            u = (u or "").strip()
            if not u: return u
            # YouTube patterns
            m = re.match(r"https?://(?:www\.)?youtube\.com/watch\?v=([^&]+)", u, re.I)
            if m: return f"https://www.youtube.com/embed/{m.group(1)}"
            m = re.match(r"https?://(?:www\.)?youtu\.be/([^?&/]+)", u, re.I)
            if m: return f"https://www.youtube.com/embed/{m.group(1)}"
            # Vimeo patterns
            m = re.match(r"https?://(?:www\.)?vimeo\.com/(\d+)", u, re.I)
            if m: return f"https://player.vimeo.com/video/{m.group(1)}"
            return u

        for raw in urls:
            src = to_embed(raw)
            if not src:  # skip blanks
                continue
            wrap = soup.new_tag("div", **{"class": "video"})
            iframe = soup.new_tag("iframe", **{
                "src": src,
                "loading": "lazy",
                "referrerpolicy": "strict-origin-when-cross-origin",
                "title": "Video",
                "allow": "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share",
                "allowfullscreen": True,
                "frameborder": "0",
            })
            wrap.append(iframe)
            grid.append(wrap)

    # ---------- Templates ----------
    def _template_html(self, mode: str) -> str:
        """Simple starter templates for collection/detail pages."""
        if mode == "collection":
            return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Collection</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="keywords" content="">
  <meta name="description" content="">
</head>
<body>
  <nav><div class="nav-container"><ul class="nav-links"></ul></div></nav>
  <header><h1>Collection</h1><p class="slogan"></p></header>
  <main>
    <section>
      <table>
        <thead><tr><th>Part No</th><th>Title</th><th>Pieces per Panel</th></tr></thead>
        <tbody></tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
        # detail page
        return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Board</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="keywords" content="">
  <meta name="description" content="">
</head>
<body>
  <nav><div class="nav-container"><ul class="nav-links"></ul></div></nav>
  <header><h1>Board</h1><p class="slogan"></p></header>
  <main>
    <div class="tab-container">
      <div class="tabs"></div>
      <div class="tab-content" id="details"><h2>Details</h2></div>
      <div class="tab-content" id="description"><h2>Description</h2></div>
      <div class="tab-content" id="simulation"><h2>Videos</h2></div>
      <div class="tab-content" id="schematic"><h2>Schematic</h2></div>
      <div class="tab-content" id="layout"><h2>Layout</h2></div>
      <div class="tab-content" id="downloads"><h2>Downloads</h2></div>
      <div class="tab-content" id="resources"><h2>Additional Resources</h2></div>
      <div class="tab-content" id="fmea"><h2>FMEA</h2></div>
      <div class="tab-content" id="testing"><h2>Testing</h2></div>
      <div class="tab-content" id="ai-seeds" data-hidden="true"></div>
    </div>
  </main>
</body>
</html>
"""

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
