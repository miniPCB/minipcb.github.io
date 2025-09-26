#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
miniPCB Website Studio — single-file PyQt5 app (AI Seeds JSON integrated)
- Crisp schematic/layout image viewing (HiDPI-aware, pixel-snapped).
- Description tab shows generated output only (no visible AI Seed).
- Optional tabs (Description, Layout, Videos, FMEA, Testing) can be included/excluded with checkboxes.
- Required tabs: Details, Schematic (Schematic tab button is active by default).
- Preserves ai-seeds JSON block and adds a large "Edit AI Seeds…" dialog.
"""

import os, sys, re, json, math, shutil, sqlite3, tempfile, datetime, threading, webbrowser
from pathlib import Path
from typing import Optional, Tuple, Dict, List
import html as html_lib

from PyQt5 import QtCore, QtGui, QtWidgets
try:
    from PyQt5 import QtWebEngineWidgets
    _HAS_WEBENGINE = True
except Exception:
    _HAS_WEBENGINE = False

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QImageReader, QPainter, QTransform, QPixmap
from PyQt5.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsPixmapItem )

# ---------- Optional deps ----------
_OPENAI_MODE = "none"   # "v1" | "v0" | "none"
try:
    from openai import OpenAI           # 1.x
    _OPENAI_MODE = "v1"
except Exception:
    try:
        import openai                   # 0.x
        _OPENAI_MODE = "v0"
    except Exception:
        pass

try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False

APP_NAME = "miniPCB Website Studio"
CONFIG_NAME = ".minipcb_studio.json"
AI_DIR_NAME = ".minipcb_ai"
DB_NAME = "ai_usage.db"
JSONL_NAME = "ai_usage.jsonl"

DARK_QSS = """
* { color: #E6E6E6; }
QMainWindow, QWidget, QDialog { background-color: #1F1F1F; }
QLabel { color: #E6E6E6; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QListWidget, QTreeView, QTableWidget, QSpinBox {
  background: #2A2A2A; color: #E6E6E6; border: 1px solid #3A3A3A; selection-background-color:#3C5DAA; selection-color:#fff;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #4C7CFF; }
QPushButton {
  background-color: #2F2F2F; border: 1px solid #4A4A4A; padding: 6px 10px; border-radius: 6px;
}
QPushButton:hover { background-color: #363636; }
QPushButton:pressed { background-color: #2A2A2A; }
QTabWidget::pane { border: 1px solid #383838; }
QTabBar::tab { background: #2A2A2A; padding: 6px 12px; border: 1px solid #383838; border-bottom: none; }
QTabBar::tab:selected { background: #353535; }
QDockWidget::title { text-align: left; padding-left: 8px; background: #252525; border-bottom: 1px solid #3A3A3A; }
QMenu { background: #252525; color: #E6E6E6; border: 1px solid #3A3A3A; }
QMenu::item:selected { background: #3C5DAA; }
QStatusBar { background: #252525; }
QTreeView::item:selected, QListWidget::item:selected { background: #3C5DAA; color: white; }
QHeaderView::section { background: #2C2C2C; color:#DDD; border: 1px solid #3A3A3A; padding: 4px; }
QScrollBar:vertical, QScrollBar:horizontal { background: #2A2A2A; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #424242; border-radius: 4px; }
QSplitter::handle { background: #2C2C2C; }
QToolTip { color: #fff; background-color: #333; border: 1px solid #555; }
"""

DEFAULT_CONFIG = {
    "dark_mode": True,
    "last_project": "",
    "images_dir": "images",
    "pdf_dir": "pdf",
    "ai": {"provider": "openai", "model": "gpt-4o-mini", "max_tokens": 1200, "temperature": 0.2},
    "regex_counters": [],
    "board_rules": {"detect_by_filename": True}
}

def human_dt() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class GlobalSettings:
    def __init__(self, filename=CONFIG_NAME):
        self.path = Path.home() / filename
        self.data = {"last_project": "", "show_html_panel": True, "autosave_sec": 30}
        self._load()
    def _load(self):
        try:
            if self.path.exists():
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:
            pass
    def save(self):
        try:
            self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        except Exception:
            pass
    def get(self, key, default=None):
        return self.data.get(key, default)
    def set(self, key, value):
        self.data[key] = value

# ---- Templates
BOARD_TEMPLATE_TABBED = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{partno} | {title}</title>
    <link rel="stylesheet" href="/styles.css">
    <link rel="icon" type="image/png" href="/favicon.png">
    <meta name="keywords" content="{keywords}">
    <meta name="description" content="{description}">
  </head>
  <body>
    <nav>
      <div class="nav-container">
        <ul class="nav-links">
          <li><a href="../index.html">Home</a></li>
        </ul>
      </div>
    </nav>
    <header>
      <h1>{partno} – {title}</h1>
      <p class="slogan">{slogan}</p>
    </header>
    <main>
      <div class="tab-container">
        <div class="tabs">
          <button class="tab" onclick="showTab('details', this)">Details</button>
          <button class="tab" onclick="showTab('description', this)">Description</button>
          <button class="tab active" onclick="showTab('schematic', this)">Schematic</button>
          <button class="tab" onclick="showTab('layout', this)">Layout</button>
          <button class="tab" onclick="showTab('downloads', this)">Downloads</button>
          <button class="tab" onclick="showTab('resources', this)">Additional Resources</button>
        </div>

        <div id="details" class="tab-content active">
          <p><strong>Part No:</strong> {partno}</p>
          <p><strong>Title:</strong> {title}</p>
        </div>

        <div id="description" class="tab-content" data-hidden="true">
          <h2>Description</h2>
          <div class="generated"><p>PLACEHOLDER</p></div>
        </div>

        <div id="schematic" class="tab-content">
          <h2>Schematic</h2>
          <div class="lightbox-container">
            <img src="../images/{schematic}" class="zoomable" alt="Schematic" onclick="openLightbox(this)">
          </div>
        </div>

        <div id="layout" class="tab-content">
          <h2>Layout</h2>
          <div class="lightbox-container">
            <img src="../images/{layout}" class="zoomable" alt="Top view of miniPCB" onclick="openLightbox(this)">
          </div>
        </div>

        <div id="downloads" class="tab-content">
          <h2>Downloads</h2>
          <ul class="download-list"></ul>
        </div>

        <div id="resources" class="tab-content" data-hidden="true">
          <h2>Additional Resources</h2>
        </div>

        <div id="fmea" class="tab-content" data-hidden="true">
          <h2>FMEA </h2>
        </div>
      </div>

      <div id="ai-seeds" class="tab-content" data-hidden="true">
        <script type="application/json" id="ai-seeds-json">{{
          "description_seed":"PLACEHOLDER",
          "fmea_seed":"PLACEHOLDER",
          "testing": {{"dtp_seed":"PLACEHOLDER","atp_seed":"PLACEHOLDER"}}
        }}</script>
      </div>

    </main>
    <footer>© {year} miniPCB. All rights reserved.</footer>
    <div id="lightbox" role="dialog" aria-label="Image viewer" aria-hidden="true">
      <img id="lightbox-img" alt="Expanded image">
    </div>
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
</html>
"""

COLLECTION_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="keywords" content="{keywords}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/styles.css">
</head>
<body>
<header><h1>{title}</h1></header>
<main>
<p>PLACEHOLDER Collection page content.</p>
</main>
<footer><small>&copy; {year} miniPCB</small></footer>
</body>
</html>
"""

AI_PROMPT_TPL = """You are an electrical engineering writing assistant.
Write succinct, accurate, technically sound content for section: {section}.
Context:
- Page Title: {title}
- Keywords: {keywords}
- Maturity Level (0=placeholder,1=immature,2=mature,3=locked): {maturity}
- Seeds / notes:
{context}

Constraints:
- Be concise, technical, non-marketing.
- Use readable plain text math where needed.
- Output raw HTML only (no <html>/<body>), to insert into the page.
"""

def write_atomic(path: Path, data: str, make_backup: bool=False) -> None:
    fd, tmpname = tempfile.mkstemp(prefix=".tmp_", suffix=".swap", dir=str(path.parent))
    os.close(fd)
    tmp = Path(tmpname)
    try:
        tmp.write_text(data, encoding="utf-8", newline="\n")
        if make_backup and path.exists():
            bak = path.with_suffix(path.suffix + ".bak")
            if bak.exists(): bak.unlink()
            shutil.copy2(str(path), str(bak))
        os.replace(str(tmp), str(path))
        if make_backup:
            bak = path.with_suffix(path.suffix + ".bak")
            if bak.exists():
                try: bak.unlink()
                except Exception: pass
    finally:
        if tmp.exists():
            try: tmp.unlink()
            except Exception: pass

def is_collection_filename(p: Path) -> bool:
    stem = p.stem
    return (len(stem) in (2,3)) and stem.isdigit() and p.suffix.lower()==".html"

def guess_images(context_dir: Path) -> Tuple[str,str]:
    cands = []
    for ext in ("*.png","*.jpg","*.jpeg","*.svg"): cands += list(context_dir.glob(ext))
    s = l = ""
    for c in cands:
        n = c.name.lower()
        if not s and ("schem" in n or "schematic" in n): s = c.name
        if not l and ("layout" in n or "components" in n or "pcb" in n): l = c.name
    return s or "SCHEMATIC.png", l or "LAYOUT.png"

# ---------- Services ----------
class ConfigService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.path = self.project_root / ".minipcb_studio.project.json"
        self.data = DEFAULT_CONFIG.copy()
        self.load()
    def load(self):
        if self.path.exists():
            try: self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except Exception: pass
    def save(self):
        try: self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        except Exception as e: print("Config save error:", e)
    def get(self, key, default=None): return self.data.get(key, default)
    def set(self, key, value): self.data[key] = value

class StatsService:
    def __init__(self, project_root: Path, regexes: List[str]):
        self.regexes = regexes or []
        self.ai_dir = project_root / AI_DIR_NAME; self.ai_dir.mkdir(exist_ok=True)
        self.db_path = self.ai_dir / DB_NAME
        self.jsonl_path = self.ai_dir / JSONL_NAME
        self._init_db()
        self.session_in = 0; self.session_out = 0; self.session_events = 0
    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TEXT NOT NULL,
              file TEXT,
              direction TEXT NOT NULL,
              raw_bytes INTEGER,
              chars INTEGER, words INTEGER, sentences INTEGER, loc INTEGER,
              est_tokens INTEGER, regex_json TEXT
            );""")
            conn.commit()
        finally:
            conn.close()
    def _count(self, text: str):
        chars = len(text)
        words = len(re.findall(r"\b[\w'-]+\b", text))
        sentences = len(re.findall(r"[\.!?]+(?:\s|$)", text)) or (1 if text.strip() else 0)
        loc = text.count("\n") + (1 if text else 0)
        est_tokens = int(max(0, round(chars/4)))
        return {"chars":chars,"words":words,"sentences":sentences,"loc":loc,"est_tokens":est_tokens}
    def log_text(self, direction: str, file: Optional[Path], text: str):
        stats = self._count(text)
        raw_bytes = len(text.encode("utf-8"))
        row = {"ts": human_dt(), "file": str(file) if file else "", "direction": direction,
               "raw_bytes": raw_bytes, **stats, "regex_json": "{}"}
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""INSERT INTO events (ts,file,direction,raw_bytes,chars,words,sentences,loc,est_tokens,regex_json)
                            VALUES (?,?,?,?,?,?,?,?,?,?);""",
                         (row["ts"],row["file"],row["direction"],row["raw_bytes"],row["chars"],
                          row["words"],row["sentences"],row["loc"],row["est_tokens"],row["regex_json"]))
            conn.commit()
        finally:
            conn.close()
        try:
            with self.jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        except Exception: pass
        if direction=="prompt": self.session_in += raw_bytes
        else: self.session_out += raw_bytes
        self.session_events += 1
    def export_csv(self, out_path: Path):
        import csv
        conn = sqlite3.connect(str(self.db_path))
        try:
            rows = conn.execute("""SELECT ts,file,direction,raw_bytes,chars,words,sentences,loc,est_tokens,regex_json
                                   FROM events ORDER BY id ASC;""").fetchall()
        finally:
            conn.close()
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["ts","file","direction","raw_bytes","chars","words","sentences","loc","est_tokens","regex_json"])
            for r in rows: w.writerow(r)

class FileService(QtCore.QObject):
    tree_changed = QtCore.pyqtSignal()
    def __init__(self, project_root: Path):
        super().__init__(); self.project_root=project_root
    def read_text(self, path: Path) -> str: return path.read_text(encoding="utf-8")
    def write_text(self, path: Path, text: str, backup=False):
        write_atomic(path, text, make_backup=backup); self.tree_changed.emit()
    def rename(self, path: Path, new_name: str) -> Path:
        new_path = path.with_name(new_name); path.rename(new_path); self.tree_changed.emit(); return new_path
    def move(self, src: Path, dest_dir: Path):
        dest_dir.mkdir(parents=True, exist_ok=True); dest = dest_dir / src.name
        shutil.move(str(src), str(dest)); self.tree_changed.emit(); return dest
    def delete(self, path: Path):
        if path.is_dir(): shutil.rmtree(path)
        else: path.unlink()
        self.tree_changed.emit()

class TemplateService:
    def __init__(self, cfg: ConfigService): self.cfg = cfg
    def new_board(self, partno="XX-000", title="Board Title", desc="", keywords="PLACEHOLDER", schematic="SCHEMATIC.png", layout="LAYOUT.png"):
        return BOARD_TEMPLATE_TABBED.format(
            partno=partno, title=title, description=desc or "PLACEHOLDER",
            keywords=keywords or "PLACEHOLDER", schematic=schematic, layout=layout,
            year=datetime.datetime.now().year, slogan="PLACEHOLDER"
        )
    def new_collection(self, title="Collection", desc="PLACEHOLDER", keywords="PLACEHOLDER"):
        return COLLECTION_TEMPLATE.format(
            title=title, description=desc or "PLACEHOLDER", keywords=keywords or "PLACEHOLDER",
            year=datetime.datetime.now().year
        )

class HtmlService:
    TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
    META_DESC_RE = re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', re.IGNORECASE | re.DOTALL)
    META_KEY_RE = re.compile(r'<meta[^>]+name=["\']keywords["\'][^>]+content=["\'](.*?)["\']', re.IGNORECASE | re.DOTALL)
    def __init__(self, cfg: ConfigService): self.cfg=cfg
    def detect_mode(self, path: Path, text: str) -> str:
        if re.search(r'(?is)<div\s+id=["\']schematic["\']', text) or re.search(r'(?is)<div\s+id=["\']layout["\']', text):
            return "board"
        if self.cfg.get("board_rules",{}).get("detect_by_filename", True):
            if is_collection_filename(path): return "collection"
        return "collection"
    def get_title(self, text: str) -> str:
        m = self.TITLE_RE.search(text); return m.group(1).strip() if m else ""
    def set_title(self, text: str, new_title: str) -> str:
        if self.TITLE_RE.search(text): return self.TITLE_RE.sub(f"<title>{new_title}</title>", text)
        return text.replace("<head>", f"<head>\n<title>{new_title}</title>\n", 1)
    def get_meta(self, text: str) -> Tuple[str,str]:
        d=k=""
        m=self.META_DESC_RE.search(text); d=m.group(1).strip() if m else d
        m=self.META_KEY_RE.search(text);  k=m.group(1).strip() if m else k
        return d,k
    def set_meta(self, text: str, desc: Optional[str], keywords: Optional[str]) -> str:
        if desc is not None:
            if not desc.strip(): desc="PLACEHOLDER"
            if self.META_DESC_RE.search(text):
                text = self.META_DESC_RE.sub(lambda m: re.sub(r'content=["\'].*?["\']', f'content="{desc}"', m.group(0), flags=re.IGNORECASE), text, count=1)
            else:
                text = text.replace("<head>", f"<head>\n<meta name=\"description\" content=\"{desc}\">", 1)
        if keywords is not None:
            if not keywords.strip(): keywords="PLACEHOLDER"
            if self.META_KEY_RE.search(text):
                text = self.META_KEY_RE.sub(lambda m: re.sub(r'content=["\'].*?["\']', f'content="{keywords}"', m.group(0), flags=re.IGNORECASE), text, count=1)
            else:
                text = text.replace("<head>", f"<head>\n<meta name=\"keywords\" content=\"{keywords}\">", 1)
        return text

class AiService(QtCore.QObject):
    finished = QtCore.pyqtSignal(str, str)  # section, html
    failed = QtCore.pyqtSignal(str)
    def __init__(self, cfg: ConfigService, stats: StatsService):
        super().__init__(); self.cfg=cfg; self.stats=stats
    def generate_async(self, section: str, title: str, keywords: str, maturity: int, context: str, file_for_stats: Optional[Path]):
        t=threading.Thread(target=self._run, args=(section,title,keywords,maturity,context,file_for_stats), daemon=True)
        t.start()
    def _run(self, section: str, title: str, keywords: str, maturity: int, context: str, file_for_stats: Optional[Path]):
        prompt = AI_PROMPT_TPL.format(section=section, title=title or "PLACEHOLDER", keywords=keywords or "PLACEHOLDER", maturity=maturity, context=context or "PLACEHOLDER")
        try: self.stats.log_text("prompt", file_for_stats, prompt)
        except Exception: pass
        model = self.cfg.get("ai",{}).get("model","gpt-4o-mini")
        temperature = float(self.cfg.get("ai",{}).get("temperature",0.2))
        max_tokens = int(self.cfg.get("ai",{}).get("max_tokens",1200))
        api_key = os.environ.get("OPENAI_API_KEY","").strip()
        base_url = os.environ.get("OPENAI_BASE_URL","").strip() or None
        try:
            text=""
            if _OPENAI_MODE == "v1" and api_key:
                client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role":"system","content":"You are a helpful engineering writing assistant."},
                        {"role":"user","content": prompt}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=120
                )
                text = (resp.choices[0].message.content or "").strip()
            elif _OPENAI_MODE == "v0" and api_key:
                openai.api_key = api_key
                if base_url: openai.api_base = base_url
                resp = openai.ChatCompletion.create(
                    model=model,
                    messages=[
                        {"role":"system","content":"You are a helpful engineering writing assistant."},
                        {"role":"user","content": prompt}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                text = resp["choices"][0]["message"]["content"].strip()
            elif _HAS_REQUESTS and api_key:
                url = (base_url.rstrip("/") if base_url else "https://api.openai.com") + "/v1/chat/completions"
                headers={"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"}
                body={"model":model,"messages":[
                    {"role":"system","content":"You are a helpful engineering writing assistant."},
                    {"role":"user","content":prompt}], "temperature":temperature, "max_tokens":max_tokens}
                r=requests.post(url, headers=headers, data=json.dumps(body), timeout=120)
                r.raise_for_status(); j=r.json(); text=j["choices"][0]["message"]["content"].strip()
            else:
                raise RuntimeError("No OpenAI client available. Install 'openai' (>=1.0) and set OPENAI_API_KEY, or ensure 'requests' is installed.")
            self.stats.log_text("response", file_for_stats, text)
            self.finished.emit(section, text)
        except Exception as e:
            self.failed.emit(str(e))

# ---------- PDF/Image viewers ----------
class PdfViewerTab(QtWidgets.QWidget):
    def __init__(self, path: Path):
        super().__init__(); self.path=path; self._zoom=1.0
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(6,6,6,6)
        top=QtWidgets.QHBoxLayout(); self.zoom_out=QtWidgets.QPushButton("–"); self.zoom_in=QtWidgets.QPushButton("+")
        self.open_external=QtWidgets.QPushButton("Open Externally")
        top.addWidget(self.zoom_out); top.addWidget(self.zoom_in); top.addStretch(1); top.addWidget(self.open_external)
        v.addLayout(top)
        if _HAS_WEBENGINE:
            self.view = QtWebEngineWidgets.QWebEngineView()
            self.view.setZoomFactor(self._zoom); self.view.load(QtCore.QUrl.fromLocalFile(str(self.path)))
            v.addWidget(self.view,1)
            self.zoom_in.clicked.connect(lambda: self._zoom_by(+0.1))
            self.zoom_out.clicked.connect(lambda: self._zoom_by(-0.1))
        else:
            msg=QtWidgets.QLabel("PyQtWebEngine not installed. Use 'Open Externally'.")
            msg.setAlignment(QtCore.Qt.AlignCenter); v.addWidget(msg,1)
            self.zoom_in.setEnabled(False); self.zoom_out.setEnabled(False)
        self.open_external.clicked.connect(lambda: webbrowser.open(str(self.path)))
    def _zoom_by(self, d: float):
        self._zoom = max(0.2, min(5.0, self._zoom+d))
        if _HAS_WEBENGINE: self.view.setZoomFactor(self._zoom)

# ---- High-quality, pixel-crisp FitImageView -----------------------
class FitImageView(QGraphicsView):
    """
    Crisp at 1:1, smooth when scaling; no cropping; no zoom creep; EXIF-aware.
    Adds: pixel-scale snap to avoid fractional blur on HiDPI screens.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._img = None
        self._pix = None
        self._fit = True
        self._min_scale = 0.05
        self._max_scale = 20.0

        scene = QGraphicsScene(self)
        self.setScene(scene)
        self.item = QGraphicsPixmapItem()
        self.item.setTransformationMode(Qt.SmoothTransformation)
        scene.addItem(self.item)

        self.setRenderHints(QPainter.SmoothPixmapTransform | QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setCacheMode(QGraphicsView.CacheNone)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)

    def load_image(self, path: str) -> None:
        rdr = QImageReader(path)
        rdr.setAutoTransform(True)
        img = rdr.read()
        if img.isNull():
            self.clear_image(); return
        self._img = img
        self._pix = QPixmap.fromImage(img)
        self._apply_pixmap()

    def set_pixmap(self, pix: QPixmap) -> None:
        if not pix or pix.isNull():
            self.clear_image(); return
        self._pix = pix
        self._img = pix.toImage()
        self._apply_pixmap()

    def clear_image(self) -> None:
        self._img = None
        self._pix = None
        self.item.setPixmap(QPixmap())
        self.scene().setSceneRect(QRectF())
        self.resetTransform()

    def set_fit_mode(self, enabled: bool) -> None:
        self._fit = bool(enabled)
        if self._fit:
            self.resetTransform()
            self._refit()

    def zoom_to_fit(self) -> None:
        self.set_fit_mode(True)

    def zoom_to_actual_pixels(self) -> None:
        self._fit = False
        self._set_abs_scale(1.0)
        self._update_sampling_hint()

    def _apply_pixmap(self) -> None:
        self.item.setPixmap(self._pix)
        self.item.setOffset(0, 0)
        self.scene().setSceneRect(self.item.boundingRect())
        self.resetTransform()
        if self._fit:
            self._refit()
        self._update_sampling_hint()

    def _refit(self) -> None:
        self.resetTransform()
        r = self.item.boundingRect()
        if not r.isEmpty():
            self.fitInView(r, Qt.KeepAspectRatio)
            self._snap_scale_to_crisp_steps()
        self._update_sampling_hint()

    def _device_px_ratio(self) -> float:
        try:
            return float(self.window().devicePixelRatioF())
        except Exception:
            return 1.0

    def _current_scale(self) -> float:
        m = self.transform()
        return 0.5 * (m.m11() + m.m22())

    def _set_abs_scale(self, s: float) -> None:
        self.setTransform(QTransform())
        self.scale(s, s)

    def _snap_scale_to_crisp_steps(self) -> None:
        s = self._current_scale()
        dpr = self._device_px_ratio()
        steps = [0.5*dpr, 1.0*dpr, 2.0*dpr, 3.0*dpr, 4.0*dpr]
        best = min(steps, key=lambda x: abs(x - s))
        if abs(best - s) <= 0.06 * best:
            self._set_abs_scale(best)

    def wheelEvent(self, e):
        if self._fit:
            self._fit = False
            self.resetTransform()

        angle = e.angleDelta().y()
        factor = 1.25 if angle > 0 else 1/1.25
        new_scale = max(self._min_scale, min(self._current_scale() * factor, self._max_scale))
        self._set_abs_scale(new_scale)
        self._snap_scale_to_crisp_steps()
        self._update_sampling_hint()
        e.accept()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._fit:
            self._refit()

    def _update_sampling_hint(self) -> None:
        s = self._current_scale()
        dpr = self._device_px_ratio()
        if abs(s - dpr) <= 0.06 * dpr:
            self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
            self.item.setTransformationMode(Qt.FastTransformation)
        else:
            self.setRenderHints(QPainter.SmoothPixmapTransform | QPainter.Antialiasing | QPainter.TextAntialiasing)
            self.item.setTransformationMode(Qt.SmoothTransformation)

class ImageViewerTab(QtWidgets.QWidget):
    def __init__(self, path: Path):
        super().__init__(); self.path=path
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(6,6,6,6)
        self.view = FitImageView()
        v.addWidget(self.view,1)
        pix = QtGui.QPixmap(str(self.path))
        if pix.isNull():
            lbl=QtWidgets.QLabel("Failed to load image."); lbl.setAlignment(QtCore.Qt.AlignCenter)
            v.addWidget(lbl,1)
        else:
            self.view.set_pixmap(pix)

# ---------- Fixed WebEngine preview ----------
if _HAS_WEBENGINE:
    class FixedWebView(QtWebEngineWidgets.QWebEngineView):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            super().setZoomFactor(1.0)
        def setZoomFactor(self, f: float):
            super().setZoomFactor(1.0)
        def wheelEvent(self, e: QtGui.QWheelEvent):
            if e.modifiers() & QtCore.Qt.ControlModifier:
                e.ignore(); return
            super().wheelEvent(e)
        def keyPressEvent(self, e: QtGui.QKeyEvent):
            if e.modifiers() & QtCore.Qt.ControlModifier and e.key() in (QtCore.Qt.Key_Plus, QtCore.Qt.Key_Minus, QtCore.Qt.Key_0):
                e.ignore(); return
            super().keyPressEvent(e)

# ---------- HTML editor + preview ----------
class HtmlEditorTab(QtWidgets.QWidget):
    content_changed = QtCore.pyqtSignal()
    def __init__(self, path: Path, project_root: Optional[Path] = None):
        super().__init__(); self.path=path; self.project_root = project_root
        self._debounce = QtCore.QTimer(self); self._debounce.setSingleShot(True); self._debounce.setInterval(350)

        lay=QtWidgets.QVBoxLayout(self); lay.setContentsMargins(6,6,6,6)

        ctr=QtWidgets.QHBoxLayout()
        self.btn_refresh = QtWidgets.QPushButton("Refresh Preview")
        self.btn_external = QtWidgets.QPushButton("Open in Browser")
        ctr.addWidget(self.btn_refresh); ctr.addStretch(1); ctr.addWidget(self.btn_external)
        lay.addLayout(ctr)

        self.inner = QtWidgets.QTabWidget()
        lay.addWidget(self.inner, 1)

        self.edit = QtWidgets.QPlainTextEdit()
        self.edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.inner.addTab(self.edit, "Editor")

        if _HAS_WEBENGINE:
            self.preview = FixedWebView()
            self._use_webengine = True
        else:
            self.preview = QtWidgets.QTextBrowser()
            self._use_webengine = False
        self.inner.addTab(self.preview, "Preview")

        txt=self.path.read_text(encoding="utf-8")
        self.edit.setPlainText(txt)
        self._render_preview()

        self.edit.textChanged.connect(self._on_text_changed)
        self._debounce.timeout.connect(self._render_preview)
        self.btn_refresh.clicked.connect(self._render_preview)
        self.btn_external.clicked.connect(lambda: webbrowser.open(str(self.path)))

    def set_panel_visible(self, visible: bool):
        for w in (self.btn_refresh, self.btn_external, self.inner):
            w.setVisible(visible)

    def text(self)->str: return self.edit.toPlainText()
    def set_text(self, text:str):
        self.edit.blockSignals(True); self.edit.setPlainText(text); self.edit.blockSignals(False)
        self._render_preview()

    def _on_text_changed(self):
        self.content_changed.emit()
        self._debounce.start()

    def _wrap_for_preview(self, html: str) -> str:
        base_href = ""
        if self.project_root:
            base_dir = self.path.parent.resolve()
            base_url = QtCore.QUrl.fromLocalFile(str(base_dir)).toString()
            if not base_url.endswith("/"): base_url += "/"
            base_href = f'<base href="{base_url}">'
        css = """
<style>
  html, body { background:#1f1f1f; color:#e6e6e6; margin:0; padding:0; }
  *, *::before, *::after { box-sizing: border-box !important; }
  img, .lightbox-container img, .zoomable {
    width: auto !important;
    max-width: 100% !important;
    height: auto !important;
    max-height: none !important;
    object-fit: contain !important;
    transform: none !important;
    zoom: 1 !important;
    display:block !important;
    image-rendering: -webkit-optimize-contrast;
    image-rendering: crisp-edges;
  }
  .lightbox-container { overflow: auto !important; max-height: none !important; }
  .tab-container { overflow: visible !important; }
</style>
<script>
  (function(){
    window.addEventListener('wheel', function(e){
      if (e.ctrlKey) { e.stopImmediatePropagation(); e.preventDefault(); }
    }, {capture:true, passive:false});
    window.addEventListener('keydown', function(e){
      if (e.ctrlKey && ['+','-','0','Equal','Minus'].includes(e.key)) { e.stopImmediatePropagation(); e.preventDefault(); }
    }, {capture:true});
  })();
</script>
"""
        head_inject = base_href + css
        if re.search(r'(?is)</head>', html):
            return re.sub(r'(?is)</head>', head_inject + "</head>", html, count=1)
        return f"<!doctype html><html><head>{head_inject}</head><body>{html}</body></html>"

    def _rewrite_abs_paths(self, html: str) -> str:
        if not self.project_root: return html
        root = self.project_root.resolve()
        def repl_attr(m):
            attr = m.group(1); url = m.group(2)
            if re.match(r'^[a-zA-Z]+:', url):
                return m.group(0)
            if not url.startswith('/'):
                return m.group(0)
            local = (root / url.lstrip('/')).resolve()
            return f'{attr}="file:///{str(local).replace("\\\\","/")}"'
        return re.sub(r'\b(src|href)\s*=\s*"([^"]+)"', repl_attr, html)

    def _render_preview(self):
        html = self.text()
        html = self._rewrite_abs_paths(html)
        wrapped = self._wrap_for_preview(html)
        if self._use_webengine:
            try:
                self.preview.setZoomFactor(1.0)
            except Exception:
                pass
            base = QtCore.QUrl.fromLocalFile(str(self.path.parent.resolve()))
            self.preview.setHtml(wrapped, base)
        else:
            self.preview.setHtml(wrapped)

# ---------- Markdown helpers ----------
def _split_md_sections(md: str) -> Dict[str, str]:
    lines = md.splitlines()
    sections: Dict[str, List[str]] = {}
    current = "_start"; sections[current]=[]
    for ln in lines:
        m = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", ln)
        if m:
            current = m.group(2).strip()
            sections[current]=[]
        else:
            sections.setdefault(current, []).append(ln)
    return {k.lower(): "\n".join(v).strip() for k,v in sections.items() if k!="_start"}

def _parse_circuit_identification(md: str) -> Dict[str, str]:
    sections = _split_md_sections(md)
    cid=None
    for key in sections:
        if key.strip().lower().startswith("circuit identification"): cid=sections[key]; break
    out: Dict[str,str]={}
    if not cid: return out
    rows = [r.strip() for r in cid.splitlines() if r.strip().startswith("|")]
    for r in rows:
        if re.match(r"^\|\s*-{2,}\s*\|", r): continue
        parts = [p.strip() for p in r.strip("|").split("|")]
        if len(parts) >= 2:
            out[parts[0]] = parts[1]
    return out

def _extract_table_after_heading(md: str, heading_startswith: str) -> str:
    sections = _split_md_sections(md)
    for title, body in sections.items():
        if title.lower().startswith(heading_startswith.lower()):
            return body.strip()
    return ""

def _extract_all_pinout_tables(md: str) -> str:
    sections = _split_md_sections(md)
    blocks=[]
    for title, body in sections.items():
        if title.lower().startswith("pinout description table"):
            blocks.append(f"# {title}\n{body.strip()}")
    return "\n\n".join(blocks).strip()

def _sanitize_rev(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9\-\_\.]", "", text).strip()

def _md_guess_paths(md_dir: Path, pn: str, rev: str) -> List[Path]:
    pn_s = pn.strip(); rev_s = _sanitize_rev(rev.strip())
    bases = [f"{pn_s}_{rev_s}_sch.md", f"{pn_s}-{rev_s}_sch.md", f"{pn_s}_{rev_s}.md", f"{pn_s}-{rev_s}.md"]
    candidates = [md_dir / b for b in bases]
    candidates += list(md_dir.glob(f"*{pn_s}*{rev_s}*sch.md"))
    candidates += list(md_dir.glob(f"*{pn_s}*{rev_s}*.md"))
    seen=set(); uniq=[]
    for c in candidates:
        k=str(c).lower()
        if k not in seen:
            seen.add(k); uniq.append(c)
    return uniq

# ---------- FMEA table widget ----------
class FmeaTableWidget(QtWidgets.QTableWidget):
    HEADERS = ["ID","Item","Failure Mode","Effect","Detection (TP#…)","Test ID","Severity","Occurrence","Detectability","RPN"]
    COL_ID, COL_ITEM, COL_MODE, COL_EFFECT, COL_DET, COL_TEST, COL_S, COL_O, COL_D, COL_RPN = range(10)

    changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(0, len(self.HEADERS), parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.horizontalHeader().setStretchLastSection(True)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx)
        self.cellChanged.connect(self._on_cell_changed)
        self._spinbox_signals = []

    def clear_rows(self):
        self.setRowCount(0)
        self._spinbox_signals.clear()

    def add_row(self, data: Optional[List[str]]=None, at: Optional[int]=None):
        if data is None: data = [""]*10
        if at is None: at = self.rowCount()
        self.insertRow(at)
        for c in (self.COL_ID,self.COL_ITEM,self.COL_MODE,self.COL_EFFECT,self.COL_DET,self.COL_TEST):
            v = data[c] if c<len(data) and str(data[c]).strip() else "PLACEHOLDER"
            self.setItem(at, c, QtWidgets.QTableWidgetItem(v))
        for c in (self.COL_S, self.COL_O, self.COL_D):
            sb = QtWidgets.QSpinBox()
            sb.setRange(1,10)
            try: sb.setValue(int(str(data[c]).strip()))
            except Exception: sb.setValue(1)
            sb.valueChanged.connect(lambda _v, row=at: self._recalc_row(row))
            self.setCellWidget(at, c, sb)
            self._spinbox_signals.append(sb)
        rpn = QtWidgets.QTableWidgetItem("")
        rpn.setFlags(rpn.flags() & ~QtCore.Qt.ItemIsEditable)
        self.setItem(at, self.COL_RPN, rpn)
        self._recalc_row(at)
        self.changed.emit()

    def insert_above(self, row: int): self.add_row([""]*10, at=max(0,row))
    def insert_below(self, row: int): self.add_row([""]*10, at=max(0,row)+1)
    def delete_row(self, row: int):
        if 0 <= row < self.rowCount():
            self.removeRow(row)
            self.changed.emit()

    def _ctx(self, pos: QtCore.QPoint):
        idx = self.indexAt(pos)
        row = idx.row() if idx.isValid() else self.rowCount()
        menu = QtWidgets.QMenu(self)
        a1 = menu.addAction("Insert Row Above")
        a2 = menu.addAction("Insert Row Below")
        menu.addSeparator()
        a3 = menu.addAction("Delete Row")
        act = menu.exec_(self.viewport().mapToGlobal(pos))
        if act == a1: self.insert_above(row)
        elif act == a2: self.insert_below(row)
        elif act == a3:
            if idx.isValid(): self.delete_row(row)

    def _on_cell_changed(self, _r, _c):
        if _c in (self.COL_S,self.COL_O,self.COL_D,self.COL_RPN):
            return
        self.changed.emit()

    def _get_spin(self, row: int, col: int) -> Optional[QtWidgets.QSpinBox]:
        w = self.cellWidget(row, col)
        return w if isinstance(w, QtWidgets.QSpinBox) else None

    def _recalc_row(self, row: int):
        s = self._get_spin(row, self.COL_S)
        o = self._get_spin(row, self.COL_O)
        d = self._get_spin(row, self.COL_D)
        if s and o and d:
            rpn = s.value()*o.value()*d.value()
            it = self.item(row, self.COL_RPN)
            if it: it.setText(str(rpn))
            else: self.setItem(row, self.COL_RPN, QtWidgets.QTableWidgetItem(str(rpn)))
            self.changed.emit()

    def to_html_table(self) -> str:
        thead = (
            "<thead><tr>"
            + "".join([f"<th>{html_lib.escape(h)}</th>" for h in self.HEADERS])
            + "</tr></thead>"
        )
        rows = []
        for r in range(self.rowCount()):
            vals = []
            for c in range(self.columnCount()):
                if c in (self.COL_S,self.COL_O,self.COL_D):
                    sb = self._get_spin(r,c)
                    vals.append(str(sb.value() if sb else 1))
                else:
                    it = self.item(r,c)
                    cell = (it.text().strip() if it else "")
                    vals.append(html_lib.escape(cell or "PLACEHOLDER"))
            try:
                s=int(vals[self.COL_S]); o=int(vals[self.COL_O]); d=int(vals[self.COL_D])
                vals[self.COL_RPN] = str(s*o*d)
            except Exception:
                pass
            rows.append("<tr>" + "".join([f"<td>{v}</td>" for v in vals]) + "</tr>")
        tbody = "<tbody>\n" + "\n".join(rows) + "\n</tbody>"
        return "<table border=\"0\" cellspacing=\"2\" cellpadding=\"0\">" + thead + tbody + "</table>"

    def load_from_html_block(self, fmea_inner_html: str):
        self.clear_rows()
        if not fmea_inner_html: 
            return
        m = re.search(r'(?is)<table\b[^>]*>(.*?)</table>', fmea_inner_html)
        if not m:
            return
        table_html = m.group(0)
        header = []
        hm = re.search(r'(?is)<thead\b[^>]*>(.*?)</thead>', table_html)
        head_body = hm.group(1) if hm else ""
        if head_body:
            cells = re.findall(r'(?is)<t[hd][^>]*>(.*?)</t[hd]>', head_body)
            header = [re.sub(r"<[^>]+>","", c).strip() for c in cells]
        else:
            first_tr = re.search(r'(?is)<tr\b[^>]*>(.*?)</tr>', table_html)
            if first_tr:
                cells = re.findall(r'(?is)<t[hd][^>]*>(.*?)</t[hd]>', first_tr.group(1))
                header = [re.sub(r"<[^>]+>","", c).strip() for c in cells]
        body_html = re.sub(r'(?is).*?<tbody\b[^>]*>(.*?)</tbody>.*', r'\1', table_html) if "<tbody" in table_html.lower() else \
                    re.sub(r'(?is)<table\b[^>]*>(.*?)</table>', r'\1', table_html)
        rows = re.findall(r'(?is)<tr\b[^>]*>(.*?)</tr>', body_html)
        for rhtml in rows:
            cells = re.findall(r'(?is)<t[hd][^>]*>(.*?)</t[hd]>', rhtml)
            values = []
            for c in cells:
                txt = re.sub(r"<[^>]+>","", c).strip()
                values.append(txt)
            while len(values) < 10:
                values.append("")
            self.add_row(values[:10])

# ---------- AI Seeds Dialog ----------
class AiSeedsDialog(QtWidgets.QDialog):
    def __init__(self, seeds: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit AI Seeds")
        self.resize(820, 620)
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(10,10,10,10)

        tabs = QtWidgets.QTabWidget()
        v.addWidget(tabs, 1)

        # Description
        w_desc = QtWidgets.QWidget(); f1=QtWidgets.QFormLayout(w_desc)
        self.ed_desc = QtWidgets.QPlainTextEdit()
        self.ed_desc.setPlaceholderText("Description seed…")
        self.ed_desc.setPlainText(seeds.get("description_seed","") or "PLACEHOLDER")
        f1.addRow("Description Seed", self.ed_desc)
        tabs.addTab(w_desc, "Description")

        # FMEA
        w_fmea = QtWidgets.QWidget(); f2=QtWidgets.QFormLayout(w_fmea)
        self.ed_fmea = QtWidgets.QPlainTextEdit()
        self.ed_fmea.setPlaceholderText("FMEA seed…")
        self.ed_fmea.setPlainText(seeds.get("fmea_seed","") or "PLACEHOLDER")
        f2.addRow("FMEA Seed", self.ed_fmea)
        tabs.addTab(w_fmea, "FMEA")

        # Testing
        w_test = QtWidgets.QWidget(); f3=QtWidgets.QFormLayout(w_test)
        testing = seeds.get("testing", {}) if isinstance(seeds.get("testing", {}), dict) else {}
        self.ed_dtp = QtWidgets.QPlainTextEdit(); self.ed_atp = QtWidgets.QPlainTextEdit()
        self.ed_dtp.setPlaceholderText("Design Test Plan seed…")
        self.ed_atp.setPlaceholderText("Acceptance/Test Procedure seed…")
        self.ed_dtp.setPlainText(testing.get("dtp_seed","") or "PLACEHOLDER")
        self.ed_atp.setPlainText(testing.get("atp_seed","") or "PLACEHOLDER")
        f3.addRow("DTP Seed", self.ed_dtp)
        f3.addRow("ATP Seed", self.ed_atp)
        tabs.addTab(w_test, "Testing")

        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Save)
        v.addWidget(bb)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)

    def result_seeds(self) -> dict:
        return {
            "description_seed": self.ed_desc.toPlainText().strip() or "PLACEHOLDER",
            "fmea_seed": self.ed_fmea.toPlainText().strip() or "PLACEHOLDER",
            "testing": {
                "dtp_seed": self.ed_dtp.toPlainText().strip() or "PLACEHOLDER",
                "atp_seed": self.ed_atp.toPlainText().strip() or "PLACEHOLDER",
            }
        }

# ---------- Board Forms ----------
class BoardForms(QtWidgets.QTabWidget):
    forms_changed = QtCore.pyqtSignal()

    def __init__(self, project_root: Path, htmlsvc):
        super().__init__()
        self.root = Path(project_root).resolve()
        self.project_root = self.root
        self.htmlsvc = htmlsvc
        self.current_html_path: Optional[Path] = None

        self._debounce = QtCore.QTimer(self); self._debounce.setSingleShot(True); self._debounce.setInterval(300)
        self._debounce.timeout.connect(lambda: self.forms_changed.emit())

        # Seeds store (mirrors ai-seeds-json)
        self.seeds = {
            "description_seed": "PLACEHOLDER",
            "fmea_seed": "PLACEHOLDER",
            "testing": {"dtp_seed":"PLACEHOLDER","atp_seed":"PLACEHOLDER"}
        }

        # ---- Metadata with subtabs
        meta = QtWidgets.QWidget()
        meta_v = QtWidgets.QVBoxLayout(meta); meta_v.setContentsMargins(6,6,6,6)
        self.meta_tabs = QtWidgets.QTabWidget()
        meta_v.addWidget(self.meta_tabs)

        # Optional tabs toggles row
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Show tabs:"))
        self.opt_description = QtWidgets.QCheckBox("Description"); self.opt_description.setChecked(True)
        self.opt_layout = QtWidgets.QCheckBox("Layout"); self.opt_layout.setChecked(True)
        self.opt_videos = QtWidgets.QCheckBox("Videos"); self.opt_videos.setChecked(True)
        self.opt_fmea = QtWidgets.QCheckBox("FMEA"); self.opt_fmea.setChecked(True)
        self.opt_testing = QtWidgets.QCheckBox("Testing"); self.opt_testing.setChecked(True)
        for cb in (self.opt_description, self.opt_layout, self.opt_videos, self.opt_fmea, self.opt_testing):
            row.addWidget(cb); cb.toggled.connect(lambda *_: self._debounce.start())
        row.addStretch(1)
        meta_v.addLayout(row)

        # Basics
        basics = QtWidgets.QWidget(); bform = QtWidgets.QFormLayout(basics)
        self.m_title = QtWidgets.QLineEdit()
        self.m_partno = QtWidgets.QLineEdit()
        self.m_rev_current = QtWidgets.QLineEdit(); self.m_rev_current.setPlaceholderText("e.g., A1-04 (used for MD import)")
        self.m_slogan = QtWidgets.QPlainTextEdit(); self.m_slogan.setPlaceholderText("One bullet per line. First line shows under H1. Default PLACEHOLDER.")
        bform.addRow("Title", self.m_title)
        bform.addRow("Part Number", self.m_partno)
        bform.addRow("Current Revision (for MD import)", self.m_rev_current)
        bform.addRow("Slogan (bulleted)", self.m_slogan)
        self.meta_tabs.addTab(basics, "Basics")

        # SEO
        seo = QtWidgets.QWidget(); sform = QtWidgets.QFormLayout(seo)
        self.m_keywords = QtWidgets.QPlainTextEdit(); self.m_keywords.setPlaceholderText("Comma-separated keywords… Default PLACEHOLDER")
        self.m_desc_list = QtWidgets.QPlainTextEdit(); self.m_desc_list.setPlaceholderText('Human description bullets. First bullet also used as meta description. Default PLACEHOLDER.')
        sform.addRow("Keywords", self.m_keywords)
        sform.addRow("Description (bulleted)", self.m_desc_list)
        self.meta_tabs.addTab(seo, "SEO")

        # Navigation — table + context menu
        nav = QtWidgets.QWidget(); nlay = QtWidgets.QVBoxLayout(nav); nlay.setContentsMargins(6,6,6,6)
        self.m_nav_table = QtWidgets.QTableWidget(0,2)
        self.m_nav_table.setHorizontalHeaderLabels(["Name","Link"])
        self.m_nav_table.horizontalHeader().setStretchLastSection(True)
        self.m_nav_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.m_nav_table.customContextMenuRequested.connect(self._nav_ctx_menu)
        nlay.addWidget(self.m_nav_table, 1)
        self.meta_tabs.addTab(nav, "Navigation")

        # Revisions
        revs = QtWidgets.QWidget(); rev_v = QtWidgets.QVBoxLayout(revs)
        self.rev_table = QtWidgets.QTableWidget(0,4); self.rev_table.setHorizontalHeaderLabels(["Date","Rev","Description","By"])
        self.rev_table.horizontalHeader().setStretchLastSection(True)
        rbtns = QtWidgets.QHBoxLayout()
        self.rev_add = QtWidgets.QPushButton("Add Row"); self.rev_del = QtWidgets.QPushButton("Remove Row")
        rbtns.addWidget(self.rev_add); rbtns.addWidget(self.rev_del); rbtns.addStretch(1)
        rev_v.addWidget(self.rev_table,1); rev_v.addLayout(rbtns)
        self.meta_tabs.addTab(revs, "Revisions")

        # EAGLE Exports
        exp = QtWidgets.QWidget(); ex_v = QtWidgets.QVBoxLayout(exp)
        ctrl = QtWidgets.QHBoxLayout()
        self.md_reimport_btn = QtWidgets.QPushButton("Re-import from ../md")
        self.md_path_label = QtWidgets.QLabel("—")
        self.md_unlock = QtWidgets.QCheckBox("Unlock editing")
        ctrl.addWidget(self.md_reimport_btn); ctrl.addStretch(1); ctrl.addWidget(self.md_path_label); ctrl.addSpacing(14); ctrl.addWidget(self.md_unlock)
        ex_v.addLayout(ctrl)
        grid = QtWidgets.QGridLayout()
        self.m_netlist = QtWidgets.QPlainTextEdit(); self.m_netlist.setReadOnly(True)
        self.m_partlist = QtWidgets.QPlainTextEdit(); self.m_partlist.setReadOnly(True)
        self.m_pinifc = QtWidgets.QPlainTextEdit(); self.m_pinifc.setReadOnly(True)
        grid.addWidget(QtWidgets.QLabel("Netlist (Markdown)"), 0,0)
        grid.addWidget(self.m_netlist, 1,0)
        grid.addWidget(QtWidgets.QLabel("Partlist (Markdown)"), 0,1)
        grid.addWidget(self.m_partlist, 1,1)
        grid.addWidget(QtWidgets.QLabel("Pin Interface Description (Markdown)"), 2,0,1,2)
        grid.addWidget(self.m_pinifc, 3,0,1,2)
        ex_v.addLayout(grid,1)
        self.meta_tabs.addTab(exp, "EAGLE Exports")

        # ---- Description tab (generated only; no AI Seed field)
        desc = QtWidgets.QWidget(); dwrap = QtWidgets.QVBoxLayout(desc); dwrap.setContentsMargins(6,6,6,6)
        topBar = QtWidgets.QHBoxLayout()
        self.d_edit_seeds_btn = QtWidgets.QPushButton("Edit AI Seeds…")
        topBar.addWidget(self.d_edit_seeds_btn); topBar.addStretch(1)
        dwrap.addLayout(topBar)
        dform = QtWidgets.QFormLayout()
        self.d_maturity = QtWidgets.QComboBox(); self.d_maturity.addItems(["0 – Placeholder","1 – Immature","2 – Mature","3 – Locked"])
        self.d_text = QtWidgets.QPlainTextEdit(); self.d_text.setPlaceholderText("Generated Description (HTML)…")
        dform.addRow("Maturity Level", self.d_maturity)
        dform.addRow("Description (generated)", self.d_text)
        dwrap.addLayout(dform)

        # ---- Videos
        vids = QtWidgets.QWidget(); vlay = QtWidgets.QVBoxLayout(vids)
        self.v_table = QtWidgets.QTableWidget(0,2); self.v_table.setHorizontalHeaderLabels(["Title","URL"])
        self.v_table.horizontalHeader().setStretchLastSection(True)
        vbtn = QtWidgets.QHBoxLayout()
        self.v_add = QtWidgets.QPushButton("Add"); self.v_del = QtWidgets.QPushButton("Remove")
        vbtn.addWidget(self.v_add); vbtn.addWidget(self.v_del); vbtn.addStretch(1)
        vlay.addWidget(self.v_table,1); vlay.addLayout(vbtn)

        # ---- Schematic
        schem = QtWidgets.QWidget(); slay = QtWidgets.QFormLayout(schem)
        self.s_img = QtWidgets.QLineEdit()
        self.s_alt = QtWidgets.QLineEdit(); self.s_alt.setText("Schematic (PLACEHOLDER)")
        self.s_browse = QtWidgets.QPushButton("Browse image…")
        self.s_view = FitImageView(); self.s_view.setMinimumHeight(160)
        h = QtWidgets.QHBoxLayout(); h.addWidget(self.s_img); h.addWidget(self.s_browse)
        w = QtWidgets.QWidget(); w.setLayout(h)
        slay.addRow("Image filename (in images/)", w)
        slay.addRow("Alt text", self.s_alt)
        slay.addRow("Preview", self.s_view)

        # ---- Layout
        layt = QtWidgets.QWidget(); lform = QtWidgets.QFormLayout(layt)
        self.l_img = QtWidgets.QLineEdit()
        self.l_alt = QtWidgets.QLineEdit(); self.l_alt.setText("Top view of miniPCB")
        self.l_browse = QtWidgets.QPushButton("Browse image…")
        self.l_view = FitImageView(); self.l_view.setMinimumHeight(160)
        h2 = QtWidgets.QHBoxLayout(); h2.addWidget(self.l_img); h2.addWidget(self.l_browse)
        w2 = QtWidgets.QWidget(); w2.setLayout(h2)
        lform.addRow("Image filename (in images/)", w2)
        lform.addRow("Alt text", self.l_alt)
        lform.addRow("Preview", self.l_view)

        # ---- Additional Resources
        res = QtWidgets.QWidget(); rlay = QtWidgets.QVBoxLayout(res)
        self.r_table = QtWidgets.QTableWidget(0,2); self.r_table.setHorizontalHeaderLabels(["Label","URL"])
        self.r_table.horizontalHeader().setStretchLastSection(True)
        rbtn = QtWidgets.QHBoxLayout(); self.r_add=QtWidgets.QPushButton("Add"); self.r_del=QtWidgets.QPushButton("Remove")
        rbtn.addWidget(self.r_add); rbtn.addWidget(self.r_del); rbtn.addStretch(1)
        rlay.addWidget(self.r_table,1); rlay.addLayout(rbtn)

        # ---- FMEA Report
        fmea = QtWidgets.QWidget(); flay = QtWidgets.QVBoxLayout(fmea)
        self.fmea_table = FmeaTableWidget()
        fbtns = QtWidgets.QHBoxLayout()
        self.f_add = QtWidgets.QPushButton("Add Row"); self.f_del = QtWidgets.QPushButton("Remove Row")
        fbtns.addWidget(self.f_add); fbtns.addWidget(self.f_del); fbtns.addStretch(1)
        flay.addWidget(self.fmea_table,1); flay.addLayout(fbtns)

        # ---- Testing
        test = QtWidgets.QWidget(); tlay = QtWidgets.QVBoxLayout(test)
        self.t_table = QtWidgets.QTableWidget(0,3); self.t_table.setHorizontalHeaderLabels(["Test No.","Name","Description"])
        self.t_table.horizontalHeader().setStretchLastSection(True)
        tbtn = QtWidgets.QHBoxLayout(); self.t_add=QtWidgets.QPushButton("Add"); self.t_del=QtWidgets.QPushButton("Remove")
        tbtn.addWidget(self.t_add); tbtn.addWidget(self.t_del); tbtn.addStretch(1)
        tlay.addWidget(self.t_table,1); tlay.addLayout(tbtn)

        # Add tabs
        self.addTab(meta, "Metadata")
        self.addTab(desc, "Description")
        self.addTab(vids, "Videos")
        self.addTab(schem, "Schematic")
        self.addTab(layt, "Layout")
        self.addTab(res, "Additional Resources")
        self.addTab(fmea, "FMEA Report")
        self.addTab(test, "Testing")

        # wiring edits
        def bump(): self._debounce.start()
        self.m_title.textChanged.connect(bump); self.m_partno.textChanged.connect(bump)
        self.m_rev_current.textChanged.connect(bump)
        self.m_slogan.textChanged.connect(bump)
        self.m_keywords.textChanged.connect(bump); self.m_desc_list.textChanged.connect(bump)
        self.m_nav_table.cellChanged.connect(lambda _r,_c: bump())
        self.rev_add.clicked.connect(self._rev_add); self.rev_del.clicked.connect(self._rev_del)
        self.rev_table.cellChanged.connect(lambda _r,_c: bump())
        self.md_reimport_btn.clicked.connect(self._manual_md_import)
        self.d_maturity.currentIndexChanged.connect(bump); self.d_text.textChanged.connect(bump)
        self.d_edit_seeds_btn.clicked.connect(self._open_ai_seeds_dialog)
        self.v_add.clicked.connect(lambda: self._add_row(self.v_table,2)); self.v_del.clicked.connect(lambda: self._del_row(self.v_table)); self.v_table.cellChanged.connect(lambda *_: bump())
        self.r_add.clicked.connect(lambda: self._add_row(self.r_table,2)); self.r_del.clicked.connect(lambda: self._del_row(self.r_table)); self.r_table.cellChanged.connect(lambda *_: bump())
        self.t_add.clicked.connect(lambda: self._add_row(self.t_table,3)); self.t_del.clicked.connect(lambda: self._del_row(self.t_table)); self.t_table.cellChanged.connect(lambda *_: bump())
        self.s_browse.clicked.connect(lambda: self._browse_img(self.s_img)); self.s_img.textChanged.connect(self._refresh_s_preview); self.s_alt.textChanged.connect(bump)
        self.l_browse.clicked.connect(lambda: self._browse_img(self.l_img)); self.l_img.textChanged.connect(self._refresh_l_preview); self.l_alt.textChanged.connect(bump)
        self.f_add.clicked.connect(lambda: (self.fmea_table.add_row([""]*10), bump()))
        self.f_del.clicked.connect(lambda: (self.fmea_table.delete_row(self.fmea_table.currentRow()), bump()))
        self.fmea_table.changed.connect(bump)

    # ----- Optional tabs helpers -----
    def _optional_flags(self) -> dict:
        return {
            "description": self.opt_description.isChecked(),
            "layout": self.opt_layout.isChecked(),
            "videos": self.opt_videos.isChecked(),
            "fmea": self.opt_fmea.isChecked(),
            "testing": self.opt_testing.isChecked(),
        }
    def _find_iframes(self, html_fragment: str) -> List[Tuple[str, str]]:
        """Return list[(title, src)] from any <iframe ...> in the given HTML."""
        out = []
        if not html_fragment:
            return out
        for m in re.finditer(r'(?is)<iframe\b[^>]*>', html_fragment):
            tag = m.group(0)
            src = re.search(r'src=["\']([^"\']+)["\']', tag)
            ttl = re.search(r'title=["\']([^"\']+)["\']', tag)
            out.append((
                html_lib.unescape(ttl.group(1)) if ttl else "",
                html_lib.unescape(src.group(1)) if src else ""
            ))
        return out

    def _slice_after_section_until_next_tab(self, html_text: str, sec_id: str, scan_limit: int = 8000) -> str:
        """
        Return HTML segment that starts just after the closing </div> of sec_id
        and ends at the next tab-content <div ...> (or up to scan_limit chars).
        """
        m = re.search(rf'(?is)<div\s+id=["\']{re.escape(sec_id)}["\'][^>]*>.*?</div\s*>', html_text)
        if not m:
            return ""
        start = m.end()
        tail = html_text[start:start + scan_limit]
        n = re.search(r'(?is)<div\s+id=["\'][a-z0-9_\-]+["\']\s+class=["\']tab-content', tail)
        return tail[:n.start()] if n else tail

    def _extract_links_anywhere(self, html_fragment: str) -> List[Tuple[str, str]]:
        """Extract <a href> links from any HTML fragment (not limited to <ul>)."""
        out = []
        if not html_fragment:
            return out
        for a in re.finditer(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_fragment):
            url = html_lib.unescape(a.group(1).strip())
            label = html_lib.unescape(re.sub(r"<[^>]+>", "", a.group(2))).strip()
            out.append((label or url, url))
        return out

    def _apply_tabs_strip(self, html: str) -> str:
        flags = self._optional_flags()
        buttons = []
        buttons.append('<button class="tab" onclick="showTab(\'details\', this)">Details</button>')
        if flags["description"]:
            buttons.append('<button class="tab" onclick="showTab(\'description\', this)">Description</button>')
        buttons.append('<button class="tab active" onclick="showTab(\'schematic\', this)">Schematic</button>')
        if flags["layout"]:
            buttons.append('<button class="tab" onclick="showTab(\'layout\', this)">Layout</button>')
        buttons.append('<button class="tab" onclick="showTab(\'downloads\', this)">Downloads</button>')
        buttons.append('<button class="tab" onclick="showTab(\'resources\', this)">Additional Resources</button>')
        if flags["videos"]:
            buttons.append('<button class="tab" onclick="showTab(\'videos\', this)">Videos</button>')
        if flags["fmea"]:
            buttons.append('<button class="tab" onclick="showTab(\'fmea\', this)">FMEA</button>')
        if flags["testing"]:
            buttons.append('<button class="tab" onclick="showTab(\'testing\', this)">Testing</button>')

        new_tabs = '<div class="tabs">\n  ' + "\n  ".join(buttons) + '\n</div>'
        return re.sub(r'(?is)<div\s+class=["\']tabs["\'][^>]*>.*?</div>', new_tabs, html, count=1)

    def _set_section_hidden(self, html: str, sec_id: str, hidden: bool) -> str:
        rx = re.compile(rf'(?is)(<div\s+id=["\']{re.escape(sec_id)}["\'])([^>]*>)')
        def repl(m):
            open_tag, rest = m.group(1), m.group(2)
            tag = open_tag + rest
            if hidden:
                if 'data-hidden="' in tag:
                    tag = re.sub(r'data-hidden=["\'](true|false)["\']', 'data-hidden="true"', tag)
                else:
                    tag = tag[:-1] + ' data-hidden="true">'
            else:
                if 'data-hidden="' in tag:
                    tag = re.sub(r'data-hidden=["\'](true|false)["\']', 'data-hidden="false"', tag)
            return tag
        return rx.sub(repl, html, count=1)

    def _open_ai_seeds_dialog(self):
        dlg = AiSeedsDialog(self.seeds, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.seeds = dlg.result_seeds()
            self._debounce.start()

    def _add_row(self, table: QtWidgets.QTableWidget, cols: int):
        r = table.rowCount(); table.insertRow(r)
        for c in range(cols): table.setItem(r, c, QtWidgets.QTableWidgetItem("PLACEHOLDER"))
    def _del_row(self, table: QtWidgets.QTableWidget):
        r = table.currentRow()
        if r >= 0: table.removeRow(r)

    def _rev_add(self):
        r = self.rev_table.rowCount(); self.rev_table.insertRow(r)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self.rev_table.setItem(r,0,QtWidgets.QTableWidgetItem(today))
        self.rev_table.setItem(r,1,QtWidgets.QTableWidgetItem("A1-01" if r==0 else "PLACEHOLDER"))
        self.rev_table.setItem(r,2,QtWidgets.QTableWidgetItem("Initial Release" if r==0 else "PLACEHOLDER"))
        self.rev_table.setItem(r,3,QtWidgets.QTableWidgetItem("N. Manteufel" if r==0 else "PLACEHOLDER"))

    def _rev_del(self):
        r = self.rev_table.currentRow()
        if r >= 0: self.rev_table.removeRow(r)

    def _nav_ctx_menu(self, pos: QtCore.QPoint):
        idx = self.m_nav_table.indexAt(pos)
        row = idx.row() if idx.isValid() else self.m_nav_table.rowCount()
        menu = QtWidgets.QMenu(self)
        act_above = menu.addAction("Add Link Above…")
        act_below = menu.addAction("Add Link Below…")
        menu.addSeparator()
        act_del = menu.addAction("Delete Link")
        chosen = menu.exec_(self.m_nav_table.viewport().mapToGlobal(pos))
        if chosen == act_above:
            self._nav_add_with_dialog(row)
        elif chosen == act_below:
            self._nav_add_with_dialog(row+1)
        elif chosen == act_del:
            if 0 <= row < self.m_nav_table.rowCount():
                self.m_nav_table.removeRow(row); self._debounce.start()

    def _nav_add_with_dialog(self, at: int):
        dlg = NavAddDialog(self.root, self.current_html_path, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            name, link = dlg.result_pair()
            at = max(0, min(at, self.m_nav_table.rowCount()))
            self.m_nav_table.insertRow(at)
            self.m_nav_table.setItem(at, 0, QtWidgets.QTableWidgetItem(name or "PLACEHOLDER"))
            self.m_nav_table.setItem(at, 1, QtWidgets.QTableWidgetItem(link or "PLACEHOLDER"))
            self._debounce.start()

    def _browse_img(self, target_line: QtWidgets.QLineEdit):
        start = str((self.root / "images").resolve())
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select image", start, "Images (*.png *.jpg *.jpeg *.svg)")
        if fn:
            try:
                rel = str(Path(fn).relative_to(self.root)).replace("\\","/")
                target_line.setText(Path(rel).name)
            except Exception:
                target_line.setText(Path(fn).name)

    def _img_rel_path(self, fname: str) -> Path:
        return (self.root / "images" / fname).resolve()

    def _refresh_s_preview(self):
        self._refresh_img_view(self.s_view, self._img_rel_path(self.s_img.text().strip()))
        self._debounce.start()

    def _refresh_l_preview(self):
        self._refresh_img_view(self.l_view, self._img_rel_path(self.l_img.text().strip()))
        self._debounce.start()

    def _refresh_img_view(self, view, abs_path):
        if not abs_path:
            view.set_pixmap(None); return
        if not Path(abs_path).exists():
            view.set_pixmap(None); return
        view.load_image(str(abs_path))
        view.set_fit_mode(True)

    # --- MD import helpers (unchanged) ---
    def _manual_md_import(self):
        if not self.current_html_path:
            QtWidgets.QMessageBox.information(self,"No file","Open a board HTML file first.")
            return
        pn = self.m_partno.text().strip()
        if not pn:
            QtWidgets.QMessageBox.information(self,"Part Number required","Enter Part Number first.")
            return
        rev = self.m_rev_current.text().strip() or self._rev_guess_current()
        if not rev:
            QtWidgets.QMessageBox.information(self,"Revision required","Enter 'Current Revision' or add a row in Revisions.")
            return
        ok = self._import_md(self.current_html_path, pn, rev, explicit=True)
        if ok:
            QtWidgets.QMessageBox.information(self,"Import complete","Imported Netlist, Partlist, and Pin Interface from MD.")
            self._debounce.start()
        else:
            QtWidgets.QMessageBox.warning(self,"Import failed","Could not find or parse ../md/PN_REV_sch.md")

    def _rev_guess_current(self) -> str:
        for r in range(self.rev_table.rowCount()):
            it = self.rev_table.item(r,1)
            if it and it.text().strip():
                return it.text().strip()
        return ""

    def _autofill_md_on_load(self, html_path: Path, pn: str):
        if not pn: return
        rev = self.m_rev_current.text().strip() or self._rev_guess_current()
        if rev and self._import_md(html_path, pn, rev, explicit=False):
            return
        md_dir = (html_path.parent / "../md").resolve()
        if md_dir.exists():
            cands = sorted(md_dir.glob(f"*{pn}*sch.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            cands += sorted(md_dir.glob(f"*{pn}*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            for c in cands:
                try:
                    md = c.read_text(encoding="utf-8")
                    idinfo = _parse_circuit_identification(md)
                    rev2 = idinfo.get("Revision","").strip()
                    if md:
                        self._fill_md_fields(md, c)
                        if not self.m_rev_current.text().strip() and rev2:
                            self.m_rev_current.setText(rev2)
                        self.md_path_label.setText(c.name)
                        return
                except Exception:
                    pass

    def _import_md(self, html_path: Path, pn: str, rev: str, explicit: bool) -> bool:
        md_dir = (html_path.parent / "../md").resolve()
        if not md_dir.exists(): return False
        for cand in _md_guess_paths(md_dir, pn, rev):
            if cand.exists():
                try:
                    md = cand.read_text(encoding="utf-8")
                    idinfo = _parse_circuit_identification(md)
                    pn_md = idinfo.get("Part Number","").strip()
                    rev_md = idinfo.get("Revision","").strip()
                    if explicit and pn_md and pn_md != pn:
                        QtWidgets.QMessageBox.warning(self,"PN mismatch", f"MD PN '{pn_md}' != form PN '{pn}'. Proceeding anyway.")
                    if explicit and rev_md and rev_md != rev:
                        QtWidgets.QMessageBox.warning(self,"REV mismatch", f"MD REV '{rev_md}' != rev '{rev}'. Proceeding anyway.")
                    self._fill_md_fields(md, cand)
                    if not self.m_rev_current.text().strip() and rev_md:
                        self.m_rev_current.setText(rev_md)
                    self.md_path_label.setText(cand.name)
                    return True
                except Exception:
                    continue
        return False

    def _fill_md_fields(self, md: str, src_path: Path):
        net = _extract_table_after_heading(md, "Netlist")
        part = _extract_table_after_heading(md, "Partlist")
        pin = _extract_all_pinout_tables(md)
        self.m_netlist.setPlainText(net or "PLACEHOLDER")
        self.m_partlist.setPlainText(part or "PLACEHOLDER")
        self.m_pinifc.setPlainText(pin or "PLACEHOLDER")

    # --- AI Seeds helpers ---
    def _parse_ai_seeds(self, html_text: str) -> dict:
        m = re.search(r'(?is)<script[^>]+id=["\']ai-seeds-json["\'][^>]*>(.*?)</script>', html_text)
        if not m:
            return {
                "description_seed":"PLACEHOLDER",
                "fmea_seed":"PLACEHOLDER",
                "testing":{"dtp_seed":"PLACEHOLDER","atp_seed":"PLACEHOLDER"}
            }
        try:
            data = json.loads(m.group(1).strip())
            if "testing" not in data or not isinstance(data["testing"], dict):
                data["testing"] = {"dtp_seed":"PLACEHOLDER","atp_seed":"PLACEHOLDER"}
            data.setdefault("description_seed","PLACEHOLDER")
            data.setdefault("fmea_seed","PLACEHOLDER")
            data["testing"].setdefault("dtp_seed","PLACEHOLDER")
            data["testing"].setdefault("atp_seed","PLACEHOLDER")
            return data
        except Exception:
            return {
                "description_seed":"PLACEHOLDER",
                "fmea_seed":"PLACEHOLDER",
                "testing":{"dtp_seed":"PLACEHOLDER","atp_seed":"PLACEHOLDER"}
            }

    def _set_ai_seeds_json(self, html_text: str, seeds: dict) -> str:
        json_text = json.dumps(seeds, ensure_ascii=False)
        if re.search(r'(?is)<script[^>]+id=["\']ai-seeds-json["\']', html_text):
            return re.sub(r'(?is)(<script[^>]+id=["\']ai-seeds-json["\'][^>]*>).*?(</script>)',
                          r'\1' + json_text + r'\2', html_text, count=1)
        block = ('<div id="ai-seeds" class="tab-content" data-hidden="true">\n'
                 f'  <script type="application/json" id="ai-seeds-json">{json_text}</script>\n'
                 '</div>\n')
        if re.search(r'(?is)</main>', html_text):
            return re.sub(r'(?is)</main>', block + r'</main>', html_text, count=1)
        return re.sub(r'(?is)</body>', block + r'</body>', html_text, count=1)

    def get_seed_for_section(self, section: str) -> str:
        sec = (section or "").strip().upper()
        if sec == "DESCRIPTION":
            return self.seeds.get("description_seed","PLACEHOLDER")
        if sec == "FMEA":
            return self.seeds.get("fmea_seed","PLACEHOLDER")
        if sec == "TESTING":
            t = self.seeds.get("testing",{})
            return f"DTP:\n{t.get('dtp_seed','PLACEHOLDER')}\n\nATP:\n{t.get('atp_seed','PLACEHOLDER')}"
        t = self.seeds.get("testing",{})
        return ("\n".join([
            self.seeds.get("description_seed","PLACEHOLDER"),
            self.seeds.get("fmea_seed","PLACEHOLDER"),
            t.get("dtp_seed","PLACEHOLDER"),
            t.get("atp_seed","PLACEHOLDER"),
        ])).strip()

    # --- Load forms from HTML ---
    def load_from_html(self, html_text: str, html_path: Path):
        self.current_html_path = html_path
        self.seeds = self._parse_ai_seeds(html_text)

        head_title = ""
        m = re.search(r"(?is)<title>\s*(.*?)\s*</title>", html_text)
        if m: head_title = html_lib.unescape(m.group(1).strip())
        pn, title_only = "", head_title
        m2 = re.match(r"\s*([A-Za-z0-9]{2,4}[A-Za-z]?-?\d{2,4})\s*[\|\-–]\s*(.+)", head_title)
        if m2:
            pn, title_only = m2.group(1).strip(), m2.group(2).strip()
        h1 = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", html_text)
        if (not pn or not title_only) and h1:
            h1_text = html_lib.unescape(re.sub(r"<[^>]+>","", h1.group(1))).strip()
            m3 = re.match(r"\s*([A-Za-z0-9]{2,4}[A-Za-z]?-?\d{2,4})\s*[–\-]\s*(.+)", h1_text)
            if m3:
                pn = pn or m3.group(1).strip()
                title_only = title_only or m3.group(2).strip()
        mk = re.search(r'(?is)<meta[^>]+name=["\']keywords["\'][^>]+content=["\'](.*?)["\']', html_text)
        keywords = html_lib.unescape(mk.group(1).strip()) if mk else ""
        msl = re.search(r'(?is)<p\s+class=["\']slogan["\'][^>]*>(.*?)</p>', html_text)
        slogan = html_lib.unescape(re.sub(r"<[^>]+>","", msl.group(1))).strip() if msl else ""

        # Description generated
        desc_block = self._get_div(html_text, "description")
        gen_html = ""
        if desc_block:
            gen_m = re.search(r'(?is)<div\s+class=["\']generated["\'][^>]*>(.*?)</div>', desc_block)
            if gen_m: gen_html = gen_m.group(1).strip()

        # Videos
        sim_block = self._get_div(html_text, "simulation") or self._get_div(html_text, "videos") or ""
        videos = []
        for im in re.finditer(r'(?is)<iframe\b[^>]*>', sim_block):
            tag = im.group(0)
            src = re.search(r'src=["\']([^"\']+)["\']', tag)
            ttl = re.search(r'title=["\']([^"\']+)["\']', tag)
            videos.append((html_lib.unescape(ttl.group(1)) if ttl else "", html_lib.unescape(src.group(1)) if src else ""))

        # Images
        schem_src, schem_alt = self._img_in_div(html_text, "schematic")
        layout_src, layout_alt = self._img_in_div(html_text, "layout")

        # Resources
        downloads_block = self._get_div(html_text, "downloads")
        res_block = self._get_div(html_text, "resources")
        resources = []
        resources += self._extract_links_from_list(downloads_block, ul_class="download-list")
        resources += self._extract_links_from_list(res_block, ul_class=None)

        # FMEA
        fmea_block_inner = self._get_div(html_text, "fmea") or ""
        self.fmea_table.load_from_html_block(fmea_block_inner)

        # Testing
        testing_block = self._get_div(html_text, "testing")
        testing_items=[]
        if testing_block:
            for li in re.findall(r'(?is)<li[^>]*>(.*?)</li>', testing_block):
                testing_items.append(html_lib.unescape(re.sub(r"<[^>]+>","", li)).strip())

        # Navigation UL
        nav_ul = re.search(r'(?is)<ul\s+class=["\']nav-links["\'][^>]*>.*?</ul>', html_text)
        nav_ul_html = nav_ul.group(0) if nav_ul else ""

        # populate basics
        self.m_title.setText(title_only or "PLACEHOLDER")
        self.m_partno.setText(pn or "PLACEHOLDER")
        self.m_slogan.setPlainText(slogan or "PLACEHOLDER")
        self.m_keywords.setPlainText(keywords or "PLACEHOLDER")
        self.d_text.setPlainText(gen_html or "<p>PLACEHOLDER</p>")

        self.v_table.setRowCount(0)
        for t, u in videos:
            r = self.v_table.rowCount(); self.v_table.insertRow(r)
            self.v_table.setItem(r, 0, QtWidgets.QTableWidgetItem(t or "PLACEHOLDER"))
            self.v_table.setItem(r, 1, QtWidgets.QTableWidgetItem(u or "PLACEHOLDER"))

        self.s_img.setText(Path(schem_src).name if schem_src else "")
        self.s_alt.setText(schem_alt or "Schematic (PLACEHOLDER)")
        self.l_img.setText(Path(layout_src).name if layout_src else "")
        self.l_alt.setText(layout_alt or "Top view of miniPCB")
        self._refresh_s_preview(); self._refresh_l_preview()

        self.r_table.setRowCount(0)
        for label, url in resources:
            r = self.r_table.rowCount(); self.r_table.insertRow(r)
            self.r_table.setItem(r, 0, QtWidgets.QTableWidgetItem(label or "PLACEHOLDER"))
            self.r_table.setItem(r, 1, QtWidgets.QTableWidgetItem(url or "PLACEHOLDER"))

        self.t_table.setRowCount(0)
        for row in testing_items:
            idx = self.t_table.rowCount(); self.t_table.insertRow(idx)
            parts = [x.strip() for x in row.split("|")]
            while len(parts) < 3: parts.append("PLACEHOLDER")
            for c in range(3):
                self.t_table.setItem(idx, c, QtWidgets.QTableWidgetItem(parts[c]))

        self._fill_nav_table(nav_ul_html)

        if self.rev_table.rowCount() == 0:
            self._rev_add()
        self.md_path_label.setText("—")
        self._autofill_md_on_load(html_path, pn or "")

        # Initialize checkboxes from HTML data-hidden flags if present
        for sec, cb in [("description", self.opt_description),
                        ("layout", self.opt_layout),
                        ("videos", self.opt_videos),
                        ("fmea", self.opt_fmea),
                        ("testing", self.opt_testing)]:
            block = self._get_full_div(html_text, sec) or ""
            hidden = bool(re.search(r'data-hidden=["\']true["\']', block or "", re.I))
            cb.setChecked(not hidden)

    # ----- apply to HTML (called by window on forms_changed) -----
    def apply_to_html(self, html_text: str) -> str:
        pn = self.m_partno.text().strip() or "PLACEHOLDER"
        title = self.m_title.text().strip() or "PLACEHOLDER"
        html_text = self._ensure_title_and_h1(html_text, pn, title)

        slogan_lines = [x.strip() for x in self.m_slogan.toPlainText().splitlines() if x.strip()]
        slogan_text = slogan_lines[0] if slogan_lines else "PLACEHOLDER"
        if re.search(r'(?is)<p\s+class=["\']slogan["\'][^>]*>.*?</p>', html_text):
            html_text = re.sub(r'(?is)<p\s+class=["\']slogan["\'][^>]*>.*?</p>',
                               f'<p class="slogan">{self._esc(slogan_text)}</p>',
                               html_text, count=1)
        else:
            html_text = re.sub(r'(?is)</header>', f'<p class="slogan">{self._esc(slogan_text)}</p></header>', html_text, count=1)

        kw = (self.m_keywords.toPlainText().replace("\n", " ").strip()) or "PLACEHOLDER"
        bullets = [x.strip() for x in self.m_desc_list.toPlainText().splitlines() if x.strip()]
        desc_meta = bullets[0] if bullets else "PLACEHOLDER"
        html_text = self.htmlsvc.set_meta(html_text, desc=desc_meta, keywords=kw)

        # Persist ai-seeds-json (seeds edited via dialog)
        html_text = self._set_ai_seeds_json(html_text, self.seeds)

        # Description: generated only
        gen_html = self.d_text.toPlainText().strip() or "<p>PLACEHOLDER</p>"
        def repl_desc(m):
            open_tag = re.search(r'(?is)<div\s+id=["\']description["\'][^>]*>', m.group(0)).group(0)
            return f'{open_tag}<h2>Description</h2>\n<div class="generated">{gen_html}</div></div>'
        html_text = re.sub(r'(?is)<div\s+id=["\']description["\'][^>]*>.*?</div\s*>', repl_desc, html_text, count=1)

        # Videos
        iframes = []
        for r in range(self.v_table.rowCount()):
            t = self.v_table.item(r, 0).text().strip() if self.v_table.item(r, 0) else "PLACEHOLDER"
            u = self.v_table.item(r, 1).text().strip() if self.v_table.item(r, 1) else ""
            if not u:
                continue
            t_attr = f' title="{self._esc(t)}"' if t else ''
            iframes.append(('<div class="video-wrapper">\n'
                            f'  <iframe src="{self._esc(u)}"{t_attr} width="560" height="315" '
                            'referrerpolicy="strict-origin-when-cross-origin" '
                            'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
                            'allowfullscreen="True" frameborder="0" loading="lazy"></iframe>\n'
                            '</div>'))
        sim_html = '<h2>Videos</h2>\n' + ("\n".join(iframes) if iframes else "<p>PLACEHOLDER</p>")
        html_text = self._set_div_inner(html_text, "simulation", sim_html)
        html_text = self._set_div_inner(html_text, "videos", sim_html)

        # Schematic/Layout images
        if self.s_img.text().strip():
            html_text = self._set_img_in_div(html_text, "schematic",
                                             self.s_img.text().strip(),
                                             alt=self.s_alt.text().strip() or "Schematic (PLACEHOLDER)")
        else:
            html_text = self._set_div_inner(html_text, "schematic", '<h2>Schematic</h2><p class="placeholder">PLACEHOLDER – schematic image not set</p>')
        if self.l_img.text().strip():
            html_text = self._set_img_in_div(html_text, "layout",
                                             self.l_img.text().strip(),
                                             alt=self.l_alt.text().strip() or "Top view of miniPCB")
        else:
            html_text = self._set_div_inner(html_text, "layout", '<h2>Layout</h2><p class="placeholder">PLACEHOLDER – layout image not set</p>')

        # Resources & Downloads
        res_items=[]
        for r in range(self.r_table.rowCount()):
            label = self.r_table.item(r, 0).text().strip() if self.r_table.item(r, 0) else "PLACEHOLDER"
            url = self.r_table.item(r, 1).text().strip() if self.r_table.item(r, 1) else ""
            if url: res_items.append((label or url, url))
        if res_items:
            ul = "<ul class=\"download-list\">\n" + "\n".join(
                [f'  <li><a rel="noopener" href="{self._esc(u)}" target="_blank">{self._esc(l)}</a></li>' for l, u in res_items]
            ) + "\n</ul>"
        else:
            ul = "<p>PLACEHOLDER</p>"
        html_text = self._set_div_inner(html_text, "downloads", "<h2>Downloads</h2>\n" + ul)
        html_text = self._set_div_inner(html_text, "resources", "<h2>Additional Resources</h2>\n" + ul)

        # FMEA table
        fmea_html = self.fmea_table.to_html_table()
        html_text = self._set_div_inner(html_text, "fmea", "<h2>FMEA </h2>\n" + (fmea_html or "<p>PLACEHOLDER</p>"))

        # Testing
        tests=[]
        for r in range(self.t_table.rowCount()):
            parts=[]
            for c in range(3):
                it=self.t_table.item(r,c); parts.append((it.text().strip() if it else "PLACEHOLDER"))
            if any([p and p!="PLACEHOLDER" for p in parts]):
                tests.append(f"<li>{self._esc(' | '.join(parts))}</li>")
        testing_inner = ("<ul>\n  " + "\n  ".join(tests) + "\n</ul>") if tests else "<p>PLACEHOLDER</p>"
        html_text = self._set_div_inner(html_text, "testing", testing_inner)

        # Navigation UL from table
        nav_ul_new = self._nav_ul_from_table()
        if nav_ul_new:
            pat = r'(?is)<ul\s+class=["\']nav-links["\'][^>]*>.*?</ul>'
            if re.search(pat, html_text):
                html_text = re.sub(pat, nav_ul_new, html_text, count=1)
            else:
                html_text = re.sub(r'(?is)(<div\s+class=["\']nav-container["\'][^>]*>)', r'\1' + nav_ul_new, html_text, count=1)

        # Optional tabs: update button row and data-hidden flags
        flags = self._optional_flags()
        html_text = self._apply_tabs_strip(html_text)
        html_text = self._set_section_hidden(html_text, "description", not flags["description"])
        html_text = self._set_section_hidden(html_text, "layout", not flags["layout"])
        html_text = self._set_section_hidden(html_text, "videos", not flags["videos"])
        html_text = self._set_section_hidden(html_text, "fmea", not flags["fmea"])
        html_text = self._set_section_hidden(html_text, "testing", not flags["testing"])

        return html_text

    # ---- internals for parsing/updating HTML blocks ----
    def _get_div(self, html: str, div_id: str) -> Optional[str]:
        m = re.search(rf'(?is)<div\s+id=["\']{re.escape(div_id)}["\'][^>]*>(.*?)</div\s*>', html)
        return m.group(1) if m else None
    def _get_full_div(self, html: str, div_id: str) -> Optional[str]:
        m = re.search(rf'(?is)(<div\s+id=["\']{re.escape(div_id)}["\'][^>]*>.*?</div\s*>)', html)
        return m.group(1) if m else None
    def _set_div_inner(self, html: str, div_id: str, new_inner_html: str) -> str:
        def repl(m):
            open_tag = re.search(r'(?is)<div\s+id=["\']%s["\'][^>]*>' % re.escape(div_id), m.group(0)).group(0)
            return f'{open_tag}{new_inner_html}</div>'
        pat = rf'(?is)<div\s+id=["\']{re.escape(div_id)}["\'][^>]*>.*?</div\s*>'
        if re.search(pat, html):
            return re.sub(pat, repl, html, count=1)
        skeleton = f'<div id="{div_id}" class="tab-content" data-hidden="true">\n{new_inner_html}\n</div>\n'
        return re.sub(r'(?is)</main>', skeleton + r'</main>', html, count=1)
    def _extract_links_from_list(self, block_html: Optional[str], ul_class: Optional[str]) -> List[Tuple[str, str]]:
        if not block_html: return []
        out=[]
        if ul_class:
            ul_m = re.search(rf'(?is)<ul[^>]+class=["\'][^"\']*{re.escape(ul_class)}[^"\']*["\'][^>]*>(.*?)</ul>', block_html)
            if not ul_m: return []
            inner = ul_m.group(1)
        else:
            ul_m = re.search(r'(?is)<ul[^>]*>(.*?)</ul>', block_html)
            if not ul_m: return []
            inner = ul_m.group(1)
        for a in re.finditer(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', inner):
            url = html_lib.unescape(a.group(1).strip())
            label = html_lib.unescape(re.sub(r"<[^>]+>","", a.group(2))).strip()
            out.append((label or url, url))
        return out
    def _img_in_div(self, html: str, div_id: str) -> Tuple[str, str]:
        blk = self._get_div(html, div_id) or ""
        m = re.search(r'(?is)<img[^>]+src=["\']([^"\']+)["\'][^>]*>', blk)
        if not m: return ("", "")
        src = html_lib.unescape(m.group(1))
        alt_m = re.search(r'(?is)alt=["\']([^"\']*)["\']', m.group(0))
        alt = html_lib.unescape(alt_m.group(1)) if alt_m else ""
        return (src, alt)
    def _img_prefix_for_div(self, html: str, div_id: str, fallback: str = "../images/") -> str:
        src, _ = self._img_in_div(html, div_id)
        if not src: return fallback
        return src.rsplit("/", 1)[0] + "/"
    def _set_img_in_div(self, html: str, div_id: str, filename: str, alt: str) -> str:
        prefix = self._img_prefix_for_div(html, div_id, fallback="../images/")
        def replace_first_img(block: str) -> str:
            def repl_img(m):
                tag = m.group(0)
                tag = re.sub(r'(?is)src=["\'][^"\']+["\']', f'src="{self._esc(prefix + filename)}"', tag, count=1)
                if re.search(r'(?is)alt=["\']', tag):
                    tag = re.sub(r'(?is)alt=["\'][^"\']*["\']', f'alt="{self._esc(alt or "PLACEHOLDER")}"', tag, count=1)
                else:
                    tag = tag[:-1] + f' alt="{self._esc(alt or "PLACEHOLDER")}"' + tag[-1:]
                tag = tag[:-1] + ' loading="lazy"' + tag[-1:]
                return tag
            return re.sub(r'(?is)<img[^>]*>', repl_img, block, count=1)
        pat = rf'(?is)(<div\s+id=["\']{re.escape(div_id)}["\'][^>]*>)(.*?)(</div\s*>)'
        if re.search(pat, html):
            return re.sub(pat, lambda m: m.group(1) + replace_first_img(m.group(2)) + m.group(3), html, count=1)
        img_html = f'<div class="lightbox-container">\n  <img src="{self._esc(prefix + filename)}" class="zoomable" alt="{self._esc(alt or "PLACEHOLDER")}" onclick="openLightbox(this)" loading="lazy">\n</div>'
        inner = f'<h2>{self._esc("Schematic" if div_id=="schematic" else "Layout")}</h2>\n{img_html}'
        return self._set_div_inner(html, div_id, inner)
    def _ensure_title_and_h1(self, html: str, pn: str, title: str) -> str:
        new_title = f"{self._esc(pn)} | {self._esc(title)}" if pn else self._esc(title)
        if re.search(r'(?is)<title>.*?</title>', html):
            html = re.sub(r'(?is)<title>.*?</title>', f'<title>{new_title}</title>', html, count=1)
        else:
            html = re.sub(r'(?is)<head>', f'<head>\n<title>{new_title}</title>', html, count=1)
        h1_text = f"{self._esc(pn)} – {self._esc(title)}" if pn else self._esc(title)
        if re.search(r'(?is)<h1[^>]*>.*?</h1>', html):
            html = re.sub(r'(?is)<h1[^>]*>.*?</h1>', f'<h1>{h1_text}</h1>', html, count=1)
        else:
            html = re.sub(r'(?is)<header[^>]*>', f'<header><h1>{h1_text}</h1>', html, count=1)
        return html
    def _fill_nav_table(self, ul_html: str):
        self.m_nav_table.setRowCount(0)
        if not ul_html: return
        for a in re.finditer(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', ul_html):
            href = html_lib.unescape(a.group(1).strip())
            label = html_lib.unescape(re.sub(r"<[^>]+>", "", a.group(2))).strip()
            r = self.m_nav_table.rowCount()
            self.m_nav_table.insertRow(r)
            self.m_nav_table.setItem(r, 0, QtWidgets.QTableWidgetItem(label or "PLACEHOLDER"))
            self.m_nav_table.setItem(r, 1, QtWidgets.QTableWidgetItem(href or "PLACEHOLDER"))
    def _nav_ul_from_table(self) -> Optional[str]:
        rows = self.m_nav_table.rowCount()
        items=[]
        for r in range(rows):
            name = self.m_nav_table.item(r,0).text().strip() if self.m_nav_table.item(r,0) else "PLACEHOLDER"
            link = self.m_nav_table.item(r,1).text().strip() if self.m_nav_table.item(r,1) else ""
            if link: items.append((name or link, link))
        if not items: return None
        ul = ['<ul class="nav-links">']
        for name, link in items:
            ul.append(f'  <li><a href="{self._esc(link)}">{self._esc(name or "PLACEHOLDER")}</a></li>')
        ul.append("</ul>")
        return "\n".join(ul)
    def _esc(self, s: str) -> str:
        return (s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))

# ---------- Navigation Add dialog ----------
class NavAddDialog(QtWidgets.QDialog):
    def __init__(self, root: Path, current_html: Optional[Path], parent=None):
        super().__init__(parent); self.setWindowTitle("Add Navigation Link"); self.resize(700, 520)
        self.root = root; self.current_html = current_html
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(10,10,10,10)
        self.search=QtWidgets.QLineEdit(); self.search.setPlaceholderText("Search pages…")
        self.list=QtWidgets.QListWidget(); self.list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.name_line = QtWidgets.QLineEdit()
        v.addWidget(self.search)
        v.addWidget(self.list,1)
        form = QtWidgets.QFormLayout()
        form.addRow("Display Name", self.name_line)
        v.addLayout(form)
        bb=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok); v.addWidget(bb)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)

        self._items=[]
        for p in sorted(root.rglob("*.html")):
            rel = str(p.relative_to(root)).replace("\\","/")
            it=QtWidgets.QListWidgetItem(rel); self.list.addItem(it); self._items.append(it)
        self.search.textChanged.connect(self._filter)
        self.list.itemSelectionChanged.connect(self._on_pick)

    def _filter(self, q: str):
        q=q.strip().lower()
        for i in self._items:
            i.setHidden(False if not q else (q not in i.text().lower()))

    def _on_pick(self):
        it = self.list.currentItem()
        if not it: return
        chosen = self.root / it.text()
        title = ""
        try:
            txt = chosen.read_text(encoding="utf-8")
            m = re.search(r"(?is)<title>\s*(.*?)\s*</title>", txt)
            title = html_lib.unescape(m.group(1).strip()) if m else ""
            m2 = re.match(r"\s*[A-Za-z0-9]{2,4}[A-Za-z]?-?\d{2,4}\s*[\|\-–]\s*(.+)", title)
            if m2: title = m2.group(1).strip()
        except Exception:
            pass
        if title: self.name_line.setText(title)

    def result_pair(self) -> Tuple[str,str]:
        it = self.list.currentItem()
        rel = it.text() if it else ""
        name = self.name_line.text().strip() or Path(rel).stem.replace("-"," ").replace("_"," ").title()
        link = rel
        if self.current_html:
            try:
                target = (self.root / rel).resolve()
                base = self.current_html.parent.resolve()
                link = os.path.relpath(str(target), str(base)).replace("\\","/")
            except Exception:
                link = rel
        return (name, link)

# ---------- Simple text viewer ----------
class TextViewerTab(QtWidgets.QWidget):
    content_changed = QtCore.pyqtSignal()
    def __init__(self, path: Path, editable: bool=True):
        super().__init__(); self.path=path
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(6,6,6,6)
        self.edit=QtWidgets.QPlainTextEdit(); self.edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        v.addWidget(self.edit,1)
        try: txt=path.read_text(encoding="utf-8")
        except Exception as e: txt=f"Error reading file: {e}"
        self.edit.setPlainText(txt); self.edit.setReadOnly(not editable); self.edit.textChanged.connect(self.content_changed)
    def text(self)->str: return self.edit.toPlainText()

# ---------- Main Window ----------
class StudioWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME); self.resize(1400, 900)

        self.gset = GlobalSettings()
        self.show_html_panel = bool(self.gset.get("show_html_panel", True))
        self.autosave_sec = int(self.gset.get("autosave_sec", 30))

        self.project_root: Optional[Path] = None
        self.cfg: Optional[ConfigService] = None
        self.stats: Optional[StatsService] = None
        self.htmlsvc: Optional[HtmlService] = None
        self.tpl: Optional[TemplateService] = None
        self.filesvc: Optional[FileService] = None
        self.ai: Optional[AiService] = None
        self.forms: Optional[BoardForms] = None

        self._ai_started_at = None
        self._ai_eta_secs = None
        self._ai_activity = ""

        self._last_edit_at: Optional[datetime.datetime] = None

        self._build_ui()
        self._apply_theme()
        self._attach_default_tree_model()

        last = self.gset.get("last_project", "")
        if last and Path(last).exists():
            self._open_project(Path(last))
        else:
            last_guess = Path.home() / "minipcb.github.io"
            if last_guess.exists():
                self._open_project(last_guess)
            else:
                self.open_project_dialog(initial=Path.home())

    def _build_ui(self):
        menubar=self.menuBar()

        # File
        filem=menubar.addMenu("&File")
        self.open_act=QtWidgets.QAction("Open Project…", self)
        self.save_act=QtWidgets.QAction("Save Current Tab", self); self.save_act.setShortcut(QtGui.QKeySequence("Ctrl+S"))
        filem.addAction(self.open_act); filem.addAction(self.save_act); filem.addSeparator()
        self.export_stats_act=QtWidgets.QAction("Export AI Usage CSV…", self); filem.addAction(self.export_stats_act)
        filem.addSeparator()
        self.exit_act=QtWidgets.QAction("E&xit", self); filem.addAction(self.exit_act)

        # New
        newm=menubar.addMenu("&New")
        self.new_board_act=QtWidgets.QAction("Board Page", self)
        self.new_collection_act=QtWidgets.QAction("Collection Page", self)
        newm.addAction(self.new_board_act); newm.addAction(self.new_collection_act)

        # AI
        aim=menubar.addMenu("&AI")
        self.ai_section_combo=QtWidgets.QComboBox(); self.ai_section_combo.addItems(["DESCRIPTION","THEORY","ANALYSIS","FMEA","WCCA","EPSA","VIDEOS","RESOURCES","TESTING"])
        self.ai_context_act=QtWidgets.QAction("Generate Selected Section…", self)
        self.ai_edit_seeds_act=QtWidgets.QAction("Edit AI Seeds…", self)
        aiw=QtWidgets.QWidget(); hl=QtWidgets.QHBoxLayout(aiw); hl.setContentsMargins(6,2,6,2)
        hl.addWidget(QtWidgets.QLabel("Section:")); hl.addWidget(self.ai_section_combo)
        corner=QtWidgets.QWidgetAction(self); corner.setDefaultWidget(aiw)
        aim.addAction(self.ai_context_act); aim.addAction(corner); aim.addSeparator(); aim.addAction(self.ai_edit_seeds_act)
        aim.addSeparator()
        self.ai_monitor_act = QtWidgets.QAction("Show Usage Monitor", self, checkable=True)
        aim.addAction(self.ai_monitor_act)

        # View
        viewm = menubar.addMenu("&View")
        self.view_html_panel_act = QtWidgets.QAction("Show HTML Panel", self, checkable=True)
        self.view_html_panel_act.setChecked(self.show_html_panel)
        viewm.addAction(self.view_html_panel_act)

        # Left: file tree
        self.tree=QtWidgets.QTreeView()
        self.tree.setHeaderHidden(False)
        self.tree.setTextElideMode(QtCore.Qt.ElideNone)
        self.tree.setIndentation(16)
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumWidth(280)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree_menu=QtWidgets.QMenu(self); self.tree_new_folder=self.tree_menu.addAction("New Folder…")
        self.tree_rename=self.tree_menu.addAction("Rename…"); self.tree_move=self.tree_menu.addAction("Move to…")
        self.tree_delete=self.tree_menu.addAction("Delete")

        # Right: tabs (HTML / other files)
        self.tabs=QtWidgets.QTabWidget(); self.tabs.setTabsClosable(True); self.tabs.setMovable(True); self.tabs.tabCloseRequested.connect(self._close_tab)

        # Board Forms dock
        self.forms_dock=QtWidgets.QDockWidget("Board Forms", self)
        self.forms_dock.setAllowedAreas(QtCore.Qt.RightDockWidgetArea); self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.forms_dock)

        # AI Usage Monitor dock
        self.ai_monitor_dock = QtWidgets.QDockWidget("AI Usage Monitor", self)
        self.ai_monitor = QtWidgets.QTextBrowser(); self.ai_monitor.setReadOnly(True)
        self.ai_monitor_dock.setWidget(self.ai_monitor)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.ai_monitor_dock)
        self.ai_monitor_dock.hide()
        self.ai_monitor_act.toggled.connect(lambda on: self.ai_monitor_dock.setVisible(on))
        self.ai_monitor_dock.visibilityChanged.connect(self.ai_monitor_act.setChecked)

        # Splitter
        self.split=QtWidgets.QSplitter(); self.split.addWidget(self.tree); self.split.addWidget(self.tabs)
        self.split.setStretchFactor(0,0); self.split.setStretchFactor(1,1); self.split.setSizes([360, 1080])
        self.setCentralWidget(self.split)

        # Status bar
        self.status=self.statusBar()
        self.saved_label = QtWidgets.QLabel("✓ Saved")
        self.ai_status_label = QtWidgets.QLabel("AI: idle")
        self.ai_progress = QtWidgets.QProgressBar(); self.ai_progress.setRange(0, 0); self.ai_progress.setFixedWidth(120); self.ai_progress.setVisible(False)
        self.status.addPermanentWidget(self.saved_label)
        self.status.addPermanentWidget(self.ai_status_label)
        self.status.addPermanentWidget(self.ai_progress)

        # timers
        self._ai_timer = QtCore.QTimer(self); self._ai_timer.setInterval(200); self._ai_timer.timeout.connect(self._ai_tick)
        self._autosave_timer = QtCore.QTimer(self); self._autosave_timer.setInterval(1000); self._autosave_timer.timeout.connect(self._autosave_tick); self._autosave_timer.start()

        # connections
        self.open_act.triggered.connect(lambda: self.open_project_dialog())
        self.exit_act.triggered.connect(self.close)
        self.save_act.triggered.connect(self._save_current_tab)
        self.export_stats_act.triggered.connect(self._export_stats)
        self.new_board_act.triggered.connect(self._new_board)
        self.new_collection_act.triggered.connect(self._new_collection)
        self.ai_context_act.triggered.connect(self._ai_generate_menu)
        self.ai_edit_seeds_act.triggered.connect(lambda: self.forms and self.forms._open_ai_seeds_dialog())
        self.view_html_panel_act.toggled.connect(self._set_show_html_panel)

        self.tree.customContextMenuRequested.connect(self._tree_context)
        self.tree.doubleClicked.connect(self._tree_open)
        self.tree_new_folder.triggered.connect(self._tree_new_folder)
        self.tree_rename.triggered.connect(self._tree_rename)
        self.tree_move.triggered.connect(self._tree_move)
        self.tree_delete.triggered.connect(self._tree_delete)

    def _apply_theme(self):
        QtWidgets.qApp.setStyle("Fusion"); QtWidgets.qApp.setStyleSheet(DARK_QSS)

    def _attach_default_tree_model(self):
        model=QtWidgets.QFileSystemModel()
        home=str(Path.home()); model.setRootPath(home)
        model.setNameFilters(["*.html","*.md","*.pdf","*.png","*.jpg","*.jpeg","*.svg","*.css","*.js"])
        model.setNameFilterDisables(False)
        self.tree.setModel(model); self.tree.setRootIndex(model.index(home))
        header = self.tree.header(); header.setStretchLastSection(False); header.setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)
        self.tree.setColumnWidth(0, 420)

    # ---- Project
    def open_project_dialog(self, initial: Optional[Path]=None):
        start=str(initial or Path.home())
        d=QtWidgets.QFileDialog.getExistingDirectory(self, "Open Project Root", start)
        if not d: return
        self._open_project(Path(d))

    def _open_project(self, root: Path):
        self.project_root=root
        self.cfg=ConfigService(root); self.cfg.set("last_project", str(root)); self.cfg.save()
        self.stats=StatsService(root, self.cfg.get("regex_counters",[]))
        self.htmlsvc=HtmlService(self.cfg); self.tpl=TemplateService(self.cfg); self.filesvc=FileService(root)
        self.filesvc.tree_changed.connect(self._refresh_tree)
        self.ai=AiService(self.cfg, self.stats)

        model=QtWidgets.QFileSystemModel(); model.setRootPath(str(root))
        model.setNameFilters(["*.html","*.md","*.pdf","*.png","*.jpg","*.jpeg","*.svg","*.css","*.js"])
        model.setNameFilterDisables(False)
        self.tree.setModel(model); self.tree.setRootIndex(model.index(str(root)))
        header = self.tree.header(); header.setStretchLastSection(False); header.setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)
        self.tree.setColumnWidth(0, 520)

        self.status.showMessage(f"Opened project: {root}", 4000)
        self.forms = BoardForms(root, self.htmlsvc)
        self.forms.forms_changed.connect(self._forms_apply_live)
        self.forms_dock.setWidget(self.forms)

        self.ai.finished.connect(self._ai_finished)
        self.ai.failed.connect(self._ai_failed)

        self.gset.set("last_project", str(root)); self.gset.save()

    def _refresh_tree(self):
        if self.project_root:
            self.tree.setRootIndex(self.tree.model().index(str(self.project_root)))

    # ---- Tree ops
    def _index_to_path(self, idx: QtCore.QModelIndex) -> Optional[Path]:
        if not idx.isValid(): return None
        return Path(self.tree.model().filePath(idx))
    def _tree_context(self, pos: QtCore.QPoint):
        idx=self.tree.indexAt(pos)
        if not idx.isValid(): return
        self.tree_menu.popup(self.tree.viewport().mapToGlobal(pos))
    def _tree_new_folder(self):
        idx=self.tree.currentIndex(); base=self._index_to_path(idx)
        if not base: return
        if not base.is_dir(): base=base.parent
        name, ok=QtWidgets.QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            (base/name.strip()).mkdir(parents=True, exist_ok=True); self.filesvc.tree_changed.emit()
    def _tree_rename(self):
        idx=self.tree.currentIndex(); p=self._index_to_path(idx)
        if not p: return
        new, ok=QtWidgets.QInputDialog.getText(self, "Rename", "New name:", text=p.name)
        if ok and new.strip(): self.filesvc.rename(p, new.strip())
    def _tree_move(self):
        idx=self.tree.currentIndex(); p=self._index_to_path(idx)
        if not p: return
        d=QtWidgets.QFileDialog.getExistingDirectory(self,"Move to…", str(self.project_root or Path.home()))
        if d: self.filesvc.move(p, Path(d))
    def _tree_delete(self):
        idx=self.tree.currentIndex(); p=self._index_to_path(idx)
        if not p: return
        if QtWidgets.QMessageBox.question(self,"Delete",f"Delete {p.name}?")==QtWidgets.QMessageBox.Yes:
            self.filesvc.delete(p); self._close_tabs_for_path(p)
    def _tree_open(self, idx: QtCore.QModelIndex):
        p=self._index_to_path(idx)
        if p: self._open_path(p)

    # ---- Tabs / open/save/autosave
    def _open_path(self, p: Path):
        for i in range(self.tabs.count()):
            if getattr(self.tabs.widget(i), "path", None)==p:
                self.tabs.setCurrentIndex(i); return
        if p.suffix.lower()==".pdf":
            tab=PdfViewerTab(p); self.tabs.addTab(tab, f"PDF: {p.name}"); self.tabs.setCurrentWidget(tab); return
        if p.suffix.lower() in (".png",".jpg",".jpeg",".svg"):
            tab=ImageViewerTab(p); self.tabs.addTab(tab, f"IMG: {p.name}"); self.tabs.setCurrentWidget(tab); return
        if p.suffix.lower()==".html":
            tab=HtmlEditorTab(p, project_root=self.project_root)
            tab.content_changed.connect(lambda: self._on_tab_edited(tab))
            self.tabs.addTab(tab, f"HTML: {p.name}"); self.tabs.setCurrentWidget(tab)
            tab.set_panel_visible(self.show_html_panel)
            text = tab.text()
            mode = self.htmlsvc.detect_mode(p, text)
            self.forms_dock.setVisible(True)
            if self.forms:
                if mode=="board":
                    self.forms.load_from_html(text, p)
                    self.forms_dock.setWindowTitle(f"Board Forms — {p.name}")
                else:
                    self.forms_dock.setWindowTitle("Board Forms (non-board layout)")
            return
        tab=TextViewerTab(p, editable=True)
        tab.content_changed.connect(lambda: self._on_tab_edited(tab))
        self.tabs.addTab(tab, f"TXT: {p.name}"); self.tabs.setCurrentWidget(tab)
        self.forms_dock.setVisible(False)

    def _on_tab_edited(self, tab: QtWidgets.QWidget):
        self._tab_dirty(tab, True)
        self._last_edit_at = datetime.datetime.now()
        self._update_saved_indicator()

    def _close_tabs_for_path(self, p: Path):
        for i in reversed(range(self.tabs.count())):
            w=self.tabs.widget(i)
            wp=getattr(w,"path",None)
            if wp and (wp==p or str(wp).startswith(str(p)+os.sep)): self.tabs.removeTab(i)

    def _close_tab(self, idx: int):
        w=self.tabs.widget(idx)
        if isinstance(w,(HtmlEditorTab, TextViewerTab)):
            if self.tabs.tabText(idx).endswith(" •"):
                r=QtWidgets.QMessageBox.question(self,"Save changes?","Save before closing?",
                    QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No|QtWidgets.QMessageBox.Cancel)
                if r==QtWidgets.QMessageBox.Cancel: return
                if r==QtWidgets.QMessageBox.Yes: self._save_tab(w)
        self.tabs.removeTab(idx)
        self._update_saved_indicator()

    def _save_current_tab(self):
        w=self.tabs.currentWidget()
        if w: self._save_tab(w)

    def _save_tab(self, tab: QtWidgets.QWidget):
        if isinstance(tab, HtmlEditorTab):
            Path(tab.path).write_text(tab.text(), encoding="utf-8")
            self._tab_dirty(tab,False); self.status.showMessage(f"Saved {Path(tab.path).name}", 3000)
        elif isinstance(tab, TextViewerTab):
            Path(tab.path).write_text(tab.text(), encoding="utf-8")
            self._tab_dirty(tab,False); self.status.showMessage(f"Saved {Path(tab.path).name}", 3000)
        self._update_saved_indicator()

    def _tab_dirty(self, tab: QtWidgets.QWidget, on: bool):
        i=self.tabs.indexOf(tab); 
        if i<0: return
        t=self.tabs.tabText(i)
        if on and not t.endswith(" •"): self.tabs.setTabText(i, t+" •")
        if not on and t.endswith(" •"): self.tabs.setTabText(i, t[:-2])

    def _autosave_tick(self):
        w=self.tabs.currentWidget()
        if not w: return
        i=self.tabs.indexOf(w)
        if i<0: return
        dirty = self.tabs.tabText(i).endswith(" •")
        if not dirty: return
        if not self._last_edit_at: return
        delta = (datetime.datetime.now() - self._last_edit_at).total_seconds()
        if delta >= self.autosave_sec:
            self._save_tab(w)

    def _update_saved_indicator(self):
        w=self.tabs.currentWidget()
        if not w:
            self.saved_label.setText("✓ Saved"); return
        i=self.tabs.indexOf(w)
        if i<0: self.saved_label.setText("✓ Saved"); return
        dirty = self.tabs.tabText(i).endswith(" •")
        self.saved_label.setText("● Unsaved" if dirty else "✓ Saved")

    # ---- New pages
    def _new_board(self):
        if not self.project_root: QtWidgets.QMessageBox.information(self,"Open project","Open a project first."); return
        name,ok=QtWidgets.QInputDialog.getText(self,"New Board Page","Filename (e.g., 04B-350.html):")
        if not (ok and name.strip()): return
        p=self.project_root / name.strip()
        if p.exists(): QtWidgets.QMessageBox.warning(self,"Exists","File already exists."); return
        imgs_dir=self.cfg.get("images_dir","images"); s,l = guess_images(self.project_root / imgs_dir)
        html=self.tpl.new_board("XX-000","Board Title","PLACEHOLDER", "PLACEHOLDER", s, l)
        Path(p).write_text(html, encoding="utf-8"); self._open_path(p)

    def _new_collection(self):
        if not self.project_root: QtWidgets.QMessageBox.information(self,"Open project","Open a project first."); return
        name,ok=QtWidgets.QInputDialog.getText(self,"New Collection Page","Filename (e.g., transistor-amplifiers.html):")
        if not (ok and name.strip()): return
        p=self.project_root / name.strip()
        if p.exists(): QtWidgets.QMessageBox.warning(self,"Exists","File already exists."); return
        html=self.tpl.new_collection("Collection","PLACEHOLDER","PLACEHOLDER")
        Path(p).write_text(html, encoding="utf-8"); self._open_path(p)

    # ---- Forms live apply
    def _forms_apply_live(self):
        tab = self.tabs.currentWidget()
        if not isinstance(tab, HtmlEditorTab): return
        before = tab.text()
        after = self.forms.apply_to_html(before)
        if after != before:
            tab.set_text(after)
            self._on_tab_edited(tab)

    # ---- AI actions
    def _ai_generate_menu(self):
        tab=self.tabs.currentWidget()
        if not isinstance(tab, HtmlEditorTab): 
            QtWidgets.QMessageBox.information(self,"Not HTML","Open an HTML page first."); return
        section=self.ai_section_combo.currentText()
        title = self.forms.m_title.text().strip() if self.forms else "PLACEHOLDER"
        keywords = self.forms.m_keywords.toPlainText().replace("\n"," ").strip() if self.forms else "PLACEHOLDER"
        maturity = self.forms.d_maturity.currentIndex() if self.forms else 1
        seed = self.forms.get_seed_for_section(section) if self.forms else "PLACEHOLDER"
        prompt_preview = AI_PROMPT_TPL.format(section=section, title=title or "PLACEHOLDER", keywords=keywords or "PLACEHOLDER", maturity=maturity, context=seed or "PLACEHOLDER")
        self._ai_start(f"generate {section}", prompt_chars=len(prompt_preview))
        self.ai.generate_async(section, title, keywords, maturity, seed, Path(tab.path))

    def _ai_tick(self):
        if not self._ai_started_at: return
        elapsed = (datetime.datetime.now() - self._ai_started_at).total_seconds()
        if self._ai_eta_secs:
            remaining = max(0.0, self._ai_eta_secs - elapsed)
            eta_txt = f" ~{int(remaining)}s"
        else:
            eta_txt = ""
        self.ai_status_label.setText(f"AI: {self._ai_activity}… {int(elapsed)}s{eta_txt}")

    def _ai_start(self, activity: str, prompt_chars: int = 0, eta_secs: Optional[float] = None):
        self._ai_activity = activity
        self._ai_started_at = datetime.datetime.now()
        self._ai_eta_secs = eta_secs if eta_secs is not None else max(5.0, (prompt_chars//4)/40.0)
        self.ai_progress.setVisible(True); self._ai_timer.start()
        self.ai_status_label.setText(f"AI: {activity}…")

    def _ai_done(self, ok: bool, extra: str = ""):
        self._ai_timer.stop(); self.ai_progress.setVisible(False)
        status = "done" if ok else "error"
        self.ai_status_label.setText(f"AI: {self._ai_activity} {status}. {extra}")
        self._ai_started_at = None; self._ai_eta_secs = None; self._ai_activity = ""

    def _ai_failed(self, msg: str):
        self._ai_done(False, extra=msg)

    def _ai_finished(self, section: str, html_fragment: str):
        tab=self.tabs.currentWidget()
        if not isinstance(tab, HtmlEditorTab): 
            self._ai_done(True); return
        if self.stats:
            xtra = f"events:{self.stats.session_events} in:{self._fmt_bytes(self.stats.session_in)} out:{self._fmt_bytes(self.stats.session_out)}"
        else:
            xtra = ""
        if section.upper()=="DESCRIPTION" and self.forms:
            frag = re.sub(r"(?is)\A\s*<(html|body)\b.*?>|</(html|body)>\s*\Z","", html_fragment).strip() or "<p>PLACEHOLDER</p>"
            self.forms.d_text.setPlainText(frag)
            QtCore.QTimer.singleShot(500, lambda: (self._save_tab(tab), self._ai_done(True, extra=xtra)))
            return
        current = tab.text()
        sec_id = section.lower()
        block = f"<div class=\"generated\">\n{(html_fragment.strip() or '<p>PLACEHOLDER</p>')}\n</div>"
        def set_section(html, sid, content):
            pat = rf'(?is)<div\s+id=["\']{re.escape(sid)}["\'][^>]*>.*?</div\s*>'
            if re.search(pat, html):
                return re.sub(pat, lambda m: re.sub(r'(?is)(<div\s+id=["\']%s["\'][^>]*>).*?(</div\s*>)' % re.escape(sid),
                                                    r'\1' + f"<h2>{sid.upper()}</h2>\n{content}" + r'\2',
                                                    m.group(0), count=1), html, count=1)
            else:
                return re.sub(r'(?is)</main>', f'<div id="{sid}" class="tab-content" data-hidden="true">\n<h2>{sid.upper()}</h2>\n{content}\n</div>\n</main>', html, count=1)
        merged = set_section(current, sec_id, block)
        if merged != current:
            tab.set_text(merged); self._on_tab_edited(tab)
        self._save_tab(tab)
        self._ai_done(True, extra=xtra)

    # ---- View toggle
    def _set_show_html_panel(self, on: bool):
        self.show_html_panel = bool(on)
        self.gset.set("show_html_panel", self.show_html_panel); self.gset.save()
        self.tabs.setVisible(self.show_html_panel)
        if self.show_html_panel:
            self.split.setSizes([360, self.width()-360])
        else:
            self.split.setSizes([self.width()-40, 1])
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, HtmlEditorTab):
                w.set_panel_visible(self.show_html_panel)

    # ---- Stats
    def _export_stats(self):
        if not self.stats: return
        out, _ = QtWidgets.QFileDialog.getSaveFileName(self,"Export AI Usage CSV", str((self.project_root or Path.home())/"ai_usage.csv"), "CSV (*.csv)")
        if not out: return
        self.stats.export_csv(Path(out)); self.status.showMessage(f"Exported stats to {out}", 4000)

    def _fmt_bytes(self, n:int)->str:
        for unit in ["B","KB","MB","GB","TB"]:
            if n<1024.0: return f"{n:.0f} {unit}"
            n/=1024.0
        return f"{n:.1f} PB"

# ---------- Entry ----------
def main():
    try:
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass
    app=QtWidgets.QApplication(sys.argv)
    QtWidgets.qApp.setStyle("Fusion")
    QtWidgets.qApp.setStyleSheet(DARK_QSS)
    win=StudioWindow(); win.show()
    sys.exit(app.exec_())

if __name__=="__main__":
    main()
