#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
miniPCB Website Studio — single-file app (PyQt5)

Highlights
- One-click run from VS Code: python website_studio.py
- Consistent dark UI (global QSS), HiDPI-safe, splitter sizing
- File tree (view/navigate/rename/move/delete) with filters
- Editors: HTML (with live preview), Markdown/Text, PDFs (zoom), images (pan/zoom)
- Create pages: Board (matches your tabbed layout), Collection
- Board Forms dock (round-trips to your real HTML):
    Metadata (Title, Part No, Slogan, Keywords, Nav Links, Rev History, Netlist, Partlist, Pin Interface)
    Description (AI Seed, Maturity, Generated HTML)
    Videos (YouTube iframes)
    Schematic (image path/alt/scale)
    Layout (image path/alt/scale)
    Additional Resources (Downloads + Resources lists)
    FMEA Report (HTML/MD)
    Testing (table)
- AI Assist (OPENAI_API_KEY): generate Description, Keywords, or any extra section; diff-first merge
- AI usage statistics: logs prompts/responses (bytes, words, regex hits, token estimate) to SQLite/JSONL; CSV export
- Non-destructive writes: updates only the specific inner HTML regions it manages

Dependencies
- pip install PyQt5
- optional: pip install PyQtWebEngine (for in-app HTML preview & PDF viewer)
- optional: pip install openai OR requests (set env OPENAI_API_KEY)

"""

import os, sys, re, json, math, shutil, sqlite3, tempfile, difflib, datetime, threading, webbrowser
from pathlib import Path
from typing import Optional, Tuple, Dict, List
import html as html_lib  # unescape existing content when parsing

# ---------- Optional deps ----------
try:
    import openai  # type: ignore
    _HAS_OPENAI = True
except Exception:
    _HAS_OPENAI = False

try:
    import requests  # fallback HTTP client if openai lib is unavailable
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False

from PyQt5 import QtCore, QtGui, QtWidgets
try:
    from PyQt5 import QtWebEngineWidgets
    _HAS_WEBENGINE = True
except Exception:
    _HAS_WEBENGINE = False

APP_NAME = "miniPCB Website Studio"
CONFIG_NAME = ".minipcb_studio.json"
AI_DIR_NAME = ".minipcb_ai"
DB_NAME = "ai_usage.db"
JSONL_NAME = "ai_usage.jsonl"

# ----------- Dark QSS (consistent) -----------
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
QDockWidget { titlebar-close-icon: url(none); titlebar-normal-icon: url(none); }
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

# ---------- Analysis/extra block constants ----------
HTML_ANALYSIS_BLOCKS_MENU = ["DESCRIPTION","THEORY","ANALYSIS","FMEA","WCCA","EPSA","VIDEOS","RESOURCES","TESTING"]

DEFAULT_CONFIG = {
    "dark_mode": True,
    "last_project": "",
    "images_dir": "images",
    "pdf_dir": "pdf",
    "ai": {"provider": "openai", "model": "gpt-4o-mini", "max_tokens": 1200, "temperature": 0.2},
    "regex_counters": [r"\bMC34063\b", r"\bSCD41\b", r"\bgain\s*=\s*[\d\.]+", r"\bVout\b"],
    "board_rules": {"detect_by_filename": True}
}

# ----------- Templates -----------
def _today():
    return datetime.datetime.now().strftime("%Y-%m-%d")

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
          <button class="tab active" onclick="showTab('schematic', this)">Schematic</button>
          <button class="tab" onclick="showTab('layout', this)">Layout</button>
          <button class="tab" onclick="showTab('simulation', this)">Videos</button>
          <button class="tab" onclick="showTab('downloads', this)">Downloads</button>
          <button class="tab" onclick="showTab('description', this)">Description</button>
        </div>

        <div id="schematic" class="tab-content active">
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

        <div id="simulation" class="tab-content">
          <h2>Videos</h2>
        </div>

        <div id="downloads" class="tab-content">
          <h2>Downloads</h2>
          <ul class="download-list">
          </ul>
        </div>

        <div id="resources" class="tab-content" data-hidden="true">
          <h2>Additional Resources</h2>
        </div>

        <div id="description" class="tab-content" data-hidden="true">
          <h2>Description</h2>
          <h3>AI Seed</h3>
          <p></p>
          <h3>AI Generated</h3>
          <div class="generated">
          </div>
        </div>

        <div id="fmea" class="tab-content" data-hidden="true">
          <h2>FMEA Report</h2>
        </div>

        <div id="testing" class="tab-content" data-hidden="true">
          <h2>Testing</h2>
          <ul></ul>
        </div>

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
<p>This is a collection page. Add links or a grid of boards below.</p>
<ul>
  <li><a href="01.html">Example Board 01</a></li>
  <li><a href="02.html">Example Board 02</a></li>
</ul>
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
- Optional notes/excerpts (AI Seed or human notes):
{context}

Constraints:
- Be concise, technical, non-marketing.
- Use readable plain text math where needed.
- Output raw HTML only (no <html>/<body>), to insert into the page.
"""

def human_dt() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ---------- Stats helpers ----------
def count_stats(text: str, regexes: List[str]) -> Dict[str, int]:
    chars = len(text)
    words = len(re.findall(r"\b[\w'-]+\b", text))
    sentences = len(re.findall(r"[\.!?]+(?:\s|$)", text)) or (1 if text.strip() else 0)
    loc = text.count("\n") + (1 if text else 0)
    est_tokens = int(max(0, round(chars/4)))
    hits = {}
    for pat in regexes:
        try: hits[pat] = len(re.findall(pat, text, flags=re.IGNORECASE))
        except re.error: hits[pat] = -1
    out = {"chars":chars,"words":words,"sentences":sentences,"loc":loc,"est_tokens":est_tokens}
    out.update({f"re:{k}":v for k,v in hits.items()})
    return out

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
    for ext in ("*.png","*.jpg","*.jpeg","*.svg"):
        cands += list(context_dir.glob(ext))
    s = l = ""
    for c in cands:
        n = c.name.lower()
        if not s and ("sch" in n or "schem" in n or "schematic" in n): s = c.name
        if not l and ("layout" in n or "brd" in n or "pcb" in n or "components" in n): l = c.name
    return s or "SCHEMATIC.png", l or "LAYOUT.png"

# ---------- Services ----------
class ConfigService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.path = self.project_root / CONFIG_NAME
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
        self.ai_dir = project_root / AI_DIR_NAME
        self.ai_dir.mkdir(exist_ok=True)
        self.db_path = self.ai_dir / DB_NAME
        self.jsonl_path = self.ai_dir / JSONL_NAME
        self._init_db()
        self.session_in = 0
        self.session_out = 0
        self.session_events = 0
    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute("""
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
    def log_text(self, direction: str, file: Optional[Path], text: str):
        stats = count_stats(text, self.regexes)
        raw_bytes = len(text.encode("utf-8"))
        row = {
            "ts": human_dt(), "file": str(file) if file else "",
            "direction": direction, "raw_bytes": raw_bytes, **stats
        }
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO events (ts,file,direction,raw_bytes,chars,words,sentences,loc,est_tokens,regex_json)
            VALUES (?,?,?,?,?,?,?,?,?,?);""",
            (row["ts"],row["file"],row["direction"],row["raw_bytes"],
             row["chars"],row["words"],row["sentences"],row["loc"],
             row["est_tokens"],
             json.dumps({k[3:]:v for k,v in stats.items() if k.startswith("re:")})
            ))
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
            cur = conn.cursor()
            rows = cur.execute("""
            SELECT ts,file,direction,raw_bytes,chars,words,sentences,loc,est_tokens,regex_json
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
    def new_board(self, partno="XX-000", title="Board Title", desc="", keywords="miniPCB, board", schematic="SCHEMATIC.png", layout="LAYOUT.png"):
        return BOARD_TEMPLATE_TABBED.format(
            partno=partno, title=title, description=desc, keywords=keywords,
            schematic=schematic, layout=layout, year=datetime.datetime.now().year, slogan="Your slogan here."
        )
    def new_collection(self, title="Collection", desc="A collection of boards.", keywords="miniPCB, collection"):
        return COLLECTION_TEMPLATE.format(
            title=title, description=desc, keywords=keywords,
            year=datetime.datetime.now().year
        )

class HtmlService:
    TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
    META_DESC_RE = re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', re.IGNORECASE | re.DOTALL)
    META_KEY_RE = re.compile(r'<meta[^>]+name=["\']keywords["\'][^>]+content=["\'](.*?)["\']', re.IGNORECASE | re.DOTALL)
    def __init__(self, cfg: ConfigService): self.cfg=cfg
    def detect_mode(self, path: Path, text: str) -> str:
        # If it has the tabbed layout ids, assume board
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
            if self.META_DESC_RE.search(text):
                text = self.META_DESC_RE.sub(lambda m: re.sub(r'content=["\'].*?["\']', f'content="{desc}"', m.group(0), flags=re.IGNORECASE), text, count=1)
            else:
                text = text.replace("<head>", f"<head>\n<meta name=\"description\" content=\"{desc}\">", 1)
        if keywords is not None:
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
        prompt = AI_PROMPT_TPL.format(section=section, title=title, keywords=keywords, maturity=maturity, context=context or "(none)")
        try: self.stats.log_text("prompt", file_for_stats, prompt)
        except Exception: pass
        model = self.cfg.get("ai",{}).get("model","gpt-4o-mini")
        temperature = float(self.cfg.get("ai",{}).get("temperature",0.2))
        max_tokens = int(self.cfg.get("ai",{}).get("max_tokens",1200))
        api_key = os.environ.get("OPENAI_API_KEY","").strip()
        try:
            text=""
            if _HAS_OPENAI and api_key:
                openai.api_key = api_key
                resp = openai.ChatCompletion.create(  # type: ignore[attr-defined]
                    model=model,
                    messages=[{"role":"system","content":"You are a helpful engineering writing assistant."},
                              {"role":"user","content": prompt}],
                    temperature=temperature, max_tokens=max_tokens
                )
                text = resp["choices"][0]["message"]["content"].strip()
            elif _HAS_REQUESTS and api_key:
                url="https://api.openai.com/v1/chat/completions"
                headers={"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"}
                body={"model":model,"messages":[
                    {"role":"system","content":"You are a helpful engineering writing assistant."},
                    {"role":"user","content":prompt}], "temperature":temperature, "max_tokens":max_tokens}
                r=requests.post(url, headers=headers, data=json.dumps(body), timeout=120)
                r.raise_for_status(); j=r.json(); text=j["choices"][0]["message"]["content"].strip()
            else:
                raise RuntimeError("Set OPENAI_API_KEY and install 'openai' or 'requests'.")
            self.stats.log_text("response", file_for_stats, text)
            self.finished.emit(section, text)
        except Exception as e:
            self.failed.emit(str(e))

# ---------- Viewers ----------
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

class ImageViewerTab(QtWidgets.QWidget):
    def __init__(self, path: Path):
        super().__init__(); self.path=path
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(6,6,6,6)
        self.view=QtWidgets.QGraphicsView()
        self.view.setRenderHints(QtGui.QPainter.Antialiasing|QtGui.QPainter.SmoothPixmapTransform)
        self.scene=QtWidgets.QGraphicsScene(self.view); self.view.setScene(self.scene); v.addWidget(self.view,1)
        self.pix=QtGui.QPixmap(str(self.path))
        if self.pix.isNull(): self.scene.addText("Failed to load image."); return
        self.item=self.scene.addPixmap(self.pix); self.view.fitInView(self.item, QtCore.Qt.KeepAspectRatio)
        self.view.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.view.wheelEvent = self._wheel_zoom
    def _wheel_zoom(self, e: QtGui.QWheelEvent):
        s = 1.25 if e.angleDelta().y()>0 else 0.8
        self.view.scale(s, s)

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

class HtmlEditorTab(QtWidgets.QWidget):
    content_changed = QtCore.pyqtSignal()
    def __init__(self, path: Path, htmlsvc: HtmlService):
        super().__init__(); self.path=path; self.htmlsvc=htmlsvc
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(6,6,6,6)
        self.splitter=QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.edit=QtWidgets.QPlainTextEdit(); self.edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.splitter.addWidget(self.edit)
        if _HAS_WEBENGINE:
            self.preview = QtWebEngineWidgets.QWebEngineView(); self.preview.setHtml("<em>Preview …</em>")
        else:
            self.preview = QtWidgets.QTextBrowser(); self.preview.setHtml("<em>Preview (basic)</em>")
        self.splitter.addWidget(self.preview); self.splitter.setSizes([900, 600])
        v.addWidget(self.splitter,1)
        txt=self.path.read_text(encoding="utf-8"); self.edit.setPlainText(txt)
        self.edit.textChanged.connect(self._edited)
    def _edited(self):
        self.content_changed.emit()
        if isinstance(self.preview, QtWidgets.QTextBrowser):
            self.preview.setHtml(self.edit.toPlainText())
        else:
            self.preview.setHtml(self.edit.toPlainText())
    def text(self)->str: return self.edit.toPlainText()
    def set_text(self, text:str):
        self.edit.blockSignals(True); self.edit.setPlainText(text); self.edit.blockSignals(False); self.preview.setHtml(text)

# ---------- Navigation link picker ----------
class NavPicker(QtWidgets.QDialog):
    def __init__(self, root: Path, parent=None):
        super().__init__(parent); self.setWindowTitle("Select Navigation Links"); self.resize(640, 520)
        v=QtWidgets.QVBoxLayout(self); v.setContentsMargins(8,8,8,8)
        self.search=QtWidgets.QLineEdit(); self.search.setPlaceholderText("Search pages…")
        self.list=QtWidgets.QListWidget(); self.list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self._all=[]
        for p in sorted(root.rglob("*.html")):
            rel = str(p.relative_to(root)).replace("\\","/")
            item=QtWidgets.QListWidgetItem(rel); self.list.addItem(item); self._all.append(item)
        v.addWidget(self.search); v.addWidget(self.list,1)
        bb=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok); v.addWidget(bb)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        self.search.textChanged.connect(self._filter)
    def _filter(self, q: str):
        q=q.strip().lower()
        for i in self._all:
            i.setHidden(False if not q else (q not in i.text().lower()))
    def selected(self)->List[str]:
        return [i.text() for i in self.list.selectedItems()]

# ---------- Board Forms ----------
class BoardForms(QtWidgets.QTabWidget):
    """Dock content for board pages. Provides load_from_html() and apply_to_html()."""
    request_generate_keywords = QtCore.pyqtSignal()
    request_generate_description = QtCore.pyqtSignal()

    def __init__(self, project_root: Path, htmlsvc: HtmlService):
        super().__init__()
        self.root = project_root
        self.htmlsvc = htmlsvc
        self.current_html_path: Optional[Path] = None

        # --- Metadata ---
        meta = QtWidgets.QWidget(); mform = QtWidgets.QFormLayout(meta); mform.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        self.m_title = QtWidgets.QLineEdit()
        self.m_partno = QtWidgets.QLineEdit()
        self.m_slogan = QtWidgets.QPlainTextEdit(); self.m_slogan.setPlaceholderText("One bullet per line (variants).")
        self.m_keywords = QtWidgets.QPlainTextEdit(); self.m_keywords.setPlaceholderText("Comma-separated keywords…")
        self.btn_keywords_ai = QtWidgets.QPushButton("AI: Generate Keywords")
        self.m_desc_list = QtWidgets.QPlainTextEdit(); self.m_desc_list.setPlaceholderText('Human description bullets (e.g., "C1 and C2 are decoupling capacitors")')
        self.m_nav = QtWidgets.QPlainTextEdit(); self.m_nav.setPlaceholderText("Top nav UL HTML (optional stash) or pick…")
        self.m_nav_btn = QtWidgets.QPushButton("Select Navigation Links…")
        # Revision history
        rev_box = QtWidgets.QGroupBox("Revision History")
        rev_lay = QtWidgets.QVBoxLayout(rev_box)
        self.rev_table = QtWidgets.QTableWidget(0,4); self.rev_table.setHorizontalHeaderLabels(["Date","Rev","Description","By"])
        self.rev_table.horizontalHeader().setStretchLastSection(True)
        rev_btns = QtWidgets.QHBoxLayout()
        self.rev_add = QtWidgets.QPushButton("Add Row"); self.rev_del = QtWidgets.QPushButton("Remove Row")
        rev_btns.addWidget(self.rev_add); rev_btns.addWidget(self.rev_del); rev_btns.addStretch(1)
        rev_lay.addWidget(self.rev_table,1); rev_lay.addLayout(rev_btns)
        # EAGLE exports
        self.m_netlist = QtWidgets.QPlainTextEdit(); self.m_netlist.setPlaceholderText("Paste EAGLE netlist (Markdown)")
        self.m_partlist = QtWidgets.QPlainTextEdit(); self.m_partlist.setPlaceholderText("Paste EAGLE partlist (Markdown)")
        self.m_pinifc = QtWidgets.QPlainTextEdit(); self.m_pinifc.setPlaceholderText("Paste EAGLE pin interface (Markdown)")
        btn_row = QtWidgets.QHBoxLayout()
        self.btn_load_net = QtWidgets.QPushButton("Load Netlist…")
        self.btn_load_part = QtWidgets.QPushButton("Load Partlist…")
        self.btn_load_pin = QtWidgets.QPushButton("Load Pin Interface…")
        btn_row.addWidget(self.btn_load_net); btn_row.addWidget(self.btn_load_part); btn_row.addWidget(self.btn_load_pin); btn_row.addStretch(1)

        mform.addRow("Title", self.m_title)
        mform.addRow("Part Number", self.m_partno)
        mform.addRow("Slogan (bulleted)", self.m_slogan)
        mform.addRow(self.btn_keywords_ai)
        mform.addRow("Key words", self.m_keywords)
        mform.addRow("Description (bulleted)", self.m_desc_list)
        hrow = QtWidgets.QHBoxLayout(); hrow.addWidget(self.m_nav); hrow.addWidget(self.m_nav_btn)
        wnav = QtWidgets.QWidget(); wnav.setLayout(hrow)
        mform.addRow("Navigation Links (picker)", wnav)
        mform.addRow(rev_box)
        mform.addRow("Netlist (Markdown)", self.m_netlist)
        mform.addRow("Partlist (Markdown)", self.m_partlist)
        mform.addRow("Pin Interface (Markdown)", self.m_pinifc)
        mform.addRow(btn_row)

        # --- Description ---
        desc = QtWidgets.QWidget(); dlay = QtWidgets.QFormLayout(desc)
        self.d_seed = QtWidgets.QPlainTextEdit(); self.d_seed.setPlaceholderText("Human-written AI Seed / constraints.")
        self.d_maturity = QtWidgets.QComboBox(); self.d_maturity.addItems(["0 – Placeholder","1 – Immature","2 – Mature","3 – Locked"])
        self.d_text = QtWidgets.QPlainTextEdit(); self.d_text.setPlaceholderText("AI Generated Description (HTML)")
        self.btn_desc_ai = QtWidgets.QPushButton("AI: Generate Description")
        dlay.addRow("AI Seed", self.d_seed)
        dlay.addRow("Maturity Level", self.d_maturity)
        dlay.addRow(self.btn_desc_ai)
        dlay.addRow("Description (generated)", self.d_text)

        # --- Videos ---
        vids = QtWidgets.QWidget(); vlay = QtWidgets.QVBoxLayout(vids)
        self.v_table = QtWidgets.QTableWidget(0,2); self.v_table.setHorizontalHeaderLabels(["Title","URL"])
        self.v_table.horizontalHeader().setStretchLastSection(True)
        vbtn = QtWidgets.QHBoxLayout()
        self.v_add = QtWidgets.QPushButton("Add"); self.v_del = QtWidgets.QPushButton("Remove")
        vbtn.addWidget(self.v_add); vbtn.addWidget(self.v_del); vbtn.addStretch(1)
        vlay.addWidget(self.v_table,1); vlay.addLayout(vbtn)

        # --- Schematic ---
        schem = QtWidgets.QWidget(); slay = QtWidgets.QFormLayout(schem)
        self.s_img = QtWidgets.QLineEdit()
        self.s_alt = QtWidgets.QLineEdit(); self.s_alt.setText("Schematic")
        self.s_scale = QtWidgets.QSpinBox(); self.s_scale.setRange(10, 200); self.s_scale.setValue(100)
        self.s_browse = QtWidgets.QPushButton("Browse image…")
        h = QtWidgets.QHBoxLayout(); h.addWidget(self.s_img); h.addWidget(self.s_browse)
        w = QtWidgets.QWidget(); w.setLayout(h)
        slay.addRow("Image filename (in images/)", w); slay.addRow("Alt text", self.s_alt); slay.addRow("Scale %", self.s_scale)

        # --- Layout ---
        layt = QtWidgets.QWidget(); lform = QtWidgets.QFormLayout(layt)
        self.l_img = QtWidgets.QLineEdit()
        self.l_alt = QtWidgets.QLineEdit(); self.l_alt.setText("Layout")
        self.l_scale = QtWidgets.QSpinBox(); self.l_scale.setRange(10, 200); self.l_scale.setValue(100)
        self.l_browse = QtWidgets.QPushButton("Browse image…")
        h2 = QtWidgets.QHBoxLayout(); h2.addWidget(self.l_img); h2.addWidget(self.l_browse)
        w2 = QtWidgets.QWidget(); w2.setLayout(h2)
        lform.addRow("Image filename (in images/)", w2); lform.addRow("Alt text", self.l_alt); lform.addRow("Scale %", self.l_scale)

        # --- Additional Resources ---
        res = QtWidgets.QWidget(); rlay = QtWidgets.QVBoxLayout(res)
        self.r_table = QtWidgets.QTableWidget(0,2); self.r_table.setHorizontalHeaderLabels(["Label","URL"])
        self.r_table.horizontalHeader().setStretchLastSection(True)
        rbtn = QtWidgets.QHBoxLayout(); self.r_add=QtWidgets.QPushButton("Add"); self.r_del=QtWidgets.QPushButton("Remove")
        rbtn.addWidget(self.r_add); rbtn.addWidget(self.r_del); rbtn.addStretch(1)
        rlay.addWidget(self.r_table,1); rlay.addLayout(rbtn)

        # --- FMEA Report ---
        fmea = QtWidgets.QWidget(); flay = QtWidgets.QVBoxLayout(fmea)
        self.f_text = QtWidgets.QPlainTextEdit(); self.f_text.setPlaceholderText("FMEA report HTML/Markdown")
        flay.addWidget(self.f_text,1)

        # --- Testing ---
        test = QtWidgets.QWidget(); tlay = QtWidgets.QVBoxLayout(test)
        self.t_table = QtWidgets.QTableWidget(0,3); self.t_table.setHorizontalHeaderLabels(["Test No.","Name","Description"])
        self.t_table.horizontalHeader().setStretchLastSection(True)
        tbtn = QtWidgets.QHBoxLayout(); self.t_add=QtWidgets.QPushButton("Add"); self.t_del=QtWidgets.QPushButton("Remove")
        tbtn.addWidget(self.t_add); tbtn.addWidget(self.t_del); tbtn.addStretch(1)
        tlay.addWidget(self.t_table,1); tlay.addLayout(tbtn)

        # Actions
        self.apply_btn = QtWidgets.QPushButton("Apply forms → HTML")
        self.reload_btn = QtWidgets.QPushButton("Reload forms ← HTML")
        actions = QtWidgets.QHBoxLayout(); actions.addWidget(self.reload_btn); actions.addStretch(1); actions.addWidget(self.apply_btn)

        # Add tabs
        self.addTab(meta, "Metadata")
        self.addTab(desc, "Description")
        self.addTab(vids, "Videos")
        self.addTab(schem, "Schematic")
        self.addTab(layt, "Layout")
        self.addTab(res, "Additional Resources")
        self.addTab(fmea, "FMEA Report")
        self.addTab(test, "Testing")

        # Bottom wrapper for dock
        wrapper = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(wrapper); outer.setContentsMargins(6,0,6,6)
        outer.addWidget(self)
        outer.addLayout(actions)
        self.container = wrapper

        # Wire-up
        self.btn_keywords_ai.clicked.connect(lambda: self.request_generate_keywords.emit())
        self.btn_desc_ai.clicked.connect(lambda: self.request_generate_description.emit())
        self.rev_add.clicked.connect(self._rev_add)
        self.rev_del.clicked.connect(self._rev_del)
        self.v_add.clicked.connect(lambda: self._add_row(self.v_table, 2))
        self.v_del.clicked.connect(lambda: self._del_row(self.v_table))
        self.r_add.clicked.connect(lambda: self._add_row(self.r_table, 2))
        self.r_del.clicked.connect(lambda: self._del_row(self.r_table))
        self.t_add.clicked.connect(lambda: self._add_row(self.t_table, 3))
        self.t_del.clicked.connect(lambda: self._del_row(self.t_table))
        self.m_nav_btn.clicked.connect(self._pick_nav)
        self.btn_load_net.clicked.connect(lambda: self._load_into(self.m_netlist))
        self.btn_load_part.clicked.connect(lambda: self._load_into(self.m_partlist))
        self.btn_load_pin.clicked.connect(lambda: self._load_into(self.m_pinifc))
        self.s_browse.clicked.connect(lambda: self._browse_img(self.s_img))
        self.l_browse.clicked.connect(lambda: self._browse_img(self.l_img))

    # ---- Small UI helpers ----
    def _add_row(self, table: QtWidgets.QTableWidget, cols: int):
        r = table.rowCount(); table.insertRow(r)
        for c in range(cols):
            table.setItem(r, c, QtWidgets.QTableWidgetItem(""))

    def _del_row(self, table: QtWidgets.QTableWidget):
        r = table.currentRow()
        if r >= 0: table.removeRow(r)

    def _rev_add(self):
        r = self.rev_table.rowCount(); self.rev_table.insertRow(r)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self.rev_table.setItem(r,0,QtWidgets.QTableWidgetItem(today))
        self.rev_table.setItem(r,1,QtWidgets.QTableWidgetItem("-"))
        self.rev_table.setItem(r,2,QtWidgets.QTableWidgetItem("Initial Release" if r==0 else ""))
        self.rev_table.setItem(r,3,QtWidgets.QTableWidgetItem("N. Manteufel" if r==0 else ""))

    def _rev_del(self):
        r = self.rev_table.currentRow()
        if r >= 0: self.rev_table.removeRow(r)

    def _pick_nav(self):
        dlg = NavPicker(self.root, self)
        if dlg.exec_()==QtWidgets.QDialog.Accepted:
            items = dlg.selected()
            if items:
                ul = "<ul>\n" + "\n".join([f'  <li><a href="/{x}">{x}</a></li>' for x in items]) + "\n</ul>"
                self.m_nav.setPlainText(ul)

    def _load_into(self, target: QtWidgets.QPlainTextEdit):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load text file", str(self.root), "Text files (*.md *.txt *.csv *.tsv);;All files (*.*)")
        if fn:
            try:
                target.setPlainText(Path(fn).read_text(encoding="utf-8"))
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Load failed", str(e))

    def _browse_img(self, target_line: QtWidgets.QLineEdit):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select image", str(self.root / "images"), "Images (*.png *.jpg *.jpeg *.svg)")
        if fn:
            try:
                rel = str(Path(fn).relative_to(self.root)).replace("\\","/")
            except Exception:
                rel = Path(fn).name
            target_line.setText(Path(rel).name)

    # ---- Parsing existing tabbed layout ----
    def load_from_html(self, html_text: str, html_path: Path):
        """Populate the forms from your existing tabbed layout."""
        self.current_html_path = html_path

        # <title> "PN | Title"
        title_tag = re.search(r"(?is)<title>\s*(.*?)\s*</title>", html_text)
        head_title = html_lib.unescape(title_tag.group(1).strip()) if title_tag else ""
        pn, title_only = "", head_title
        m = re.match(r"\s*([A-Za-z0-9]{2,4}[A-Za-z]?-?\d{2,4})\s*[\|\-–]\s*(.+)", head_title)
        if m:
            pn, title_only = m.group(1).strip(), m.group(2).strip()
        # backup from <h1>
        h1 = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", html_text)
        h1_text = html_lib.unescape(self._plain(h1.group(1))) if h1 else ""
        if not pn or not title_only:
            m2 = re.match(r"\s*([A-Za-z0-9]{2,4}[A-Za-z]?-?\d{2,4})\s*[–\-]\s*(.+)", h1_text)
            if m2:
                pn = pn or m2.group(1).strip()
                title_only = title_only or m2.group(2).strip()

        # Keywords
        mk = re.search(r'(?is)<meta[^>]+name=["\']keywords["\'][^>]+content=["\'](.*?)["\']', html_text)
        keywords = html_lib.unescape(mk.group(1).strip()) if mk else ""

        # Slogan
        msl = re.search(r'(?is)<p\s+class=["\']slogan["\'][^>]*>(.*?)</p>', html_text)
        slogan = html_lib.unescape(self._plain(msl.group(1))) if msl else ""

        # Description
        desc_block = self._get_div(html_text, "description")
        ai_seed = ""
        gen_html = ""
        if desc_block:
            seed_m = re.search(r'(?is)<h3[^>]*>\s*AI\s*Seed\s*</h3>\s*<p[^>]*>(.*?)</p>', desc_block)
            if seed_m: ai_seed = html_lib.unescape(self._plain(seed_m.group(1)))
            gen_m = re.search(r'(?is)<div\s+class=["\']generated["\'][^>]*>(.*?)</div>', desc_block)
            if gen_m: gen_html = gen_m.group(1).strip()

        # Videos
        sim_block = self._get_div(html_text, "simulation") or ""
        videos = []
        for im in re.finditer(r'(?is)<iframe\b[^>]*>', sim_block):
            tag = im.group(0)
            src = re.search(r'src=["\']([^"\']+)["\']', tag)
            ttl = re.search(r'title=["\']([^"\']+)["\']', tag)
            videos.append((html_lib.unescape(ttl.group(1)) if ttl else "", html_lib.unescape(src.group(1)) if src else ""))

        # Images
        schem_src, schem_alt = self._img_in_div(html_text, "schematic")
        layout_src, layout_alt = self._img_in_div(html_text, "layout")

        # Downloads + Resources
        downloads_block = self._get_div(html_text, "downloads")
        res_block = self._get_div(html_text, "resources")
        resources = []
        resources += self._extract_links_from_list(downloads_block, ul_class="download-list")
        resources += self._extract_links_from_list(res_block, ul_class=None)

        # FMEA (optional)
        fmea_block = self._get_div(html_text, "fmea")
        fmea_txt = fmea_block.strip() if fmea_block else ""
        # Testing (optional)
        testing_block = self._get_div(html_text, "testing")
        testing_items = []
        if testing_block:
            for li in re.findall(r'(?is)<li[^>]*>(.*?)</li>', testing_block):
                testing_items.append(html_lib.unescape(self._plain(li)))

        # Nav stash (top nav)
        nav_ul = re.search(r'(?is)<ul\s+class=["\']nav-links["\'][^>]*>(.*?)</ul>', html_text)
        nav_ul_html = nav_ul.group(0) if nav_ul else ""

        # Fill widgets
        self.m_title.setText(title_only)
        self.m_partno.setText(pn)
        self.m_slogan.setPlainText(slogan)
        self.m_keywords.setPlainText(keywords)
        self.d_seed.setPlainText(ai_seed)
        self.d_text.setPlainText(gen_html)

        self.v_table.setRowCount(0)
        for t, u in videos:
            r = self.v_table.rowCount(); self.v_table.insertRow(r)
            self.v_table.setItem(r, 0, QtWidgets.QTableWidgetItem(t))
            self.v_table.setItem(r, 1, QtWidgets.QTableWidgetItem(u))

        self.s_img.setText(Path(schem_src).name if schem_src else "")
        self.s_alt.setText(schem_alt or "Schematic")
        self.l_img.setText(Path(layout_src).name if layout_src else "")
        self.l_alt.setText(layout_alt or "Layout")

        self.r_table.setRowCount(0)
        for label, url in resources:
            r = self.r_table.rowCount(); self.r_table.insertRow(r)
            self.r_table.setItem(r, 0, QtWidgets.QTableWidgetItem(label))
            self.r_table.setItem(r, 1, QtWidgets.QTableWidgetItem(url))

        self.f_text.setPlainText(fmea_txt)

        self.t_table.setRowCount(0)
        for row in testing_items:
            idx = self.t_table.rowCount(); self.t_table.insertRow(idx)
            # naive split: "T-001 | Name | Desc" → 3 cols
            parts = [x.strip() for x in row.split("|")]
            while len(parts) < 3: parts.append("")
            for c in range(3):
                self.t_table.setItem(idx, c, QtWidgets.QTableWidgetItem(parts[c]))

        self.m_nav.setPlainText(nav_ul_html)

        if self.rev_table.rowCount() == 0:
            self._rev_add()

    # ---- Write back to tabbed layout (non-destructive) ----
    def apply_to_html(self, html_text: str) -> str:
        pn = self.m_partno.text().strip()
        title = self.m_title.text().strip() or "Untitled"
        html_text = self._ensure_title_and_h1(html_text, pn, title)

        # Slogan
        slogan_lines = [x.strip() for x in self.m_slogan.toPlainText().splitlines() if x.strip()]
        slogan_text = slogan_lines[0] if slogan_lines else ""
        if slogan_text:
            if re.search(r'(?is)<p\s+class=["\']slogan["\'][^>]*>.*?</p>', html_text):
                html_text = re.sub(
                    r'(?is)<p\s+class=["\']slogan["\'][^>]*>.*?</p>',
                    f'<p class="slogan">{self._esc(slogan_text)}</p>',
                    html_text, count=1
                )
            else:
                html_text = re.sub(r'(?is)</header>', f'<p class="slogan">{self._esc(slogan_text)}</p></header>', html_text, count=1)

        # Keywords meta
        kw = self.m_keywords.toPlainText().replace("\n", " ").strip()
        html_text = self._set_meta_keywords(html_text, kw)

        # Description: AI Seed + Generated
        seed_html = f"<p>{self._esc(self.d_seed.toPlainText().strip())}</p>"
        gen_html = self.d_text.toPlainText().strip() or "<p></p>"

        def repl_seed(m):
            block = m.group(0)
            block = re.sub(r'(?is)(<h3[^>]*>\s*AI\s*Seed\s*</h3>\s*)<p[^>]*>.*?</p>',
                           r'\1' + seed_html, block, count=1)
            return block
        html_text = re.sub(r'(?is)<div\s+id=["\']description["\'][^>]*>.*?</div\s*>', repl_seed, html_text, count=1)

        def repl_gen(m):
            block = m.group(0)
            block = re.sub(r'(?is)(<div\s+class=["\']generated["\'][^>]*>).*?(</div>)',
                           r'\1' + gen_html + r'\2', block, count=1)
            return block
        html_text = re.sub(r'(?is)<div\s+id=["\']description["\'][^>]*>.*?</div\s*>', repl_gen, html_text, count=1)
        if not re.search(r'(?is)<div\s+id=["\']description["\']', html_text):
            skeleton = (
                '<div id="description" class="tab-content" data-hidden="true">\n'
                '  <h2>Description</h2>\n'
                '  <h3>AI Seed</h3>\n'
                f'  {seed_html}\n'
                '  <h3>AI Generated</h3>\n'
                f'  <div class="generated">{gen_html}</div>\n'
                '</div>\n'
            )
            html_text = re.sub(r'(?is)</main>', skeleton + r'</main>', html_text, count=1)

        # Videos
        iframes = []
        for r in range(self.v_table.rowCount()):
            t = self.v_table.item(r, 0).text().strip() if self.v_table.item(r, 0) else ""
            u = self.v_table.item(r, 1).text().strip() if self.v_table.item(r, 1) else ""
            if not u: continue
            t_attr = f' title="{self._esc(t)}"' if t else ''
            ifr = (f'<div class="video-wrapper">\n'
                   f'  <iframe src="{self._esc(u)}"{t_attr} width="560" height="315" '
                   f'referrerpolicy="strict-origin-when-cross-origin" '
                   f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
                   f'allowfullscreen="True" frameborder="0"></iframe>\n'
                   f'</div>')
            iframes.append(ifr)
        sim_html = '<h2>Videos</h2>\n' + "\n".join(iframes) if iframes else '<h2>Videos</h2>'
        html_text = self._set_div_inner(html_text, "simulation", sim_html)

        # Schematic/Layout images: replace src (preserve path prefix)
        if self.s_img.text().strip():
            html_text = self._set_img_in_div(html_text, "schematic",
                                             self.s_img.text().strip(),
                                             alt=self.s_alt.text().strip() or "Schematic")
        if self.l_img.text().strip():
            html_text = self._set_img_in_div(html_text, "layout",
                                             self.l_img.text().strip(),
                                             alt=self.l_alt.text().strip() or "Layout")

        # Additional Resources → downloads/resources
        res_items = []
        for r in range(self.r_table.rowCount()):
            label = self.r_table.item(r, 0).text().strip() if self.r_table.item(r, 0) else ""
            url = self.r_table.item(r, 1).text().strip() if self.r_table.item(r, 1) else ""
            if url:
                res_items.append((label or url, url))
        if res_items:
            dl_ul = "<ul class=\"download-list\">\n" + "\n".join(
                [f'  <li><a rel="noopener" href="{self._esc(u)}" target="_blank">{self._esc(l)}</a></li>' for l, u in res_items]
            ) + "\n</ul>"
            html_text = self._set_div_inner(html_text, "downloads", "<h2>Downloads</h2>\n" + dl_ul)
            html_text = self._set_div_inner(html_text, "resources", "<h2>Additional Resources</h2>\n" + dl_ul)

        # FMEA → #fmea (create if missing)
        fmea_html = self.f_text.toPlainText().strip()
        if fmea_html:
            html_text = self._set_div_inner(html_text, "fmea", "<h2>FMEA Report</h2>\n" + fmea_html)

        # Testing → #testing ul
        tests=[]
        for r in range(self.t_table.rowCount()):
            parts=[]
            for c in range(3):
                it=self.t_table.item(r,c); parts.append(it.text().strip() if it else "")
            if any(parts):
                tests.append(f"<li>{self._esc(' | '.join(parts))}</li>")
        if tests:
            testing_inner = "<h2>Testing</h2>\n<ul>\n  " + "\n  ".join(tests) + "\n</ul>"
            html_text = self._set_div_inner(html_text, "testing", testing_inner)

        # Engineering stash (hidden) for Netlist/Partlist/Pin Interface
        eng = []
        if self.m_netlist.toPlainText().strip():
            eng.append("<h3>Netlist</h3>\n<pre>\n" + self._esc(self.m_netlist.toPlainText()) + "\n</pre>")
        if self.m_partlist.toPlainText().strip():
            eng.append("<h3>Partlist</h3>\n<pre>\n" + self._esc(self.m_partlist.toPlainText()) + "\n</pre>")
        if self.m_pinifc.toPlainText().strip():
            eng.append("<h3>Pin Interface Description</h3>\n<pre>\n" + self._esc(self.m_pinifc.toPlainText()) + "\n</pre>")
        if eng:
            html_text = self._set_div_inner(html_text, "engineering",
                                            '<h2>Engineering</h2>\n' + "\n".join(eng))

        return html_text

    # ---- HTML helpers ----
    def _get_div(self, html: str, div_id: str) -> Optional[str]:
        m = re.search(rf'(?is)<div\s+id=["\']{re.escape(div_id)}["\'][^>]*>(.*?)</div\s*>', html)
        return m.group(1) if m else None

    def _set_div_inner(self, html: str, div_id: str, new_inner_html: str) -> str:
        def repl(m):
            open_tag = re.search(r'(?is)<div\s+id=["\']%s["\'][^>]*>' % re.escape(div_id), m.group(0)).group(0)
            return f'{open_tag}{new_inner_html}</div>'
        pat = rf'(?is)<div\s+id=["\']{re.escape(div_id)}["\'][^>]*>.*?</div\s*>'
        if re.search(pat, html):
            return re.sub(pat, repl, html, count=1)
        # create before </main>
        skeleton = f'<div id="{div_id}" class="tab-content" data-hidden="true">\n{new_inner_html}\n</div>\n'
        return re.sub(r'(?is)</main>', skeleton + r'</main>', html, count=1)

    def _extract_links_from_list(self, block_html: Optional[str], ul_class: Optional[str]) -> List[Tuple[str, str]]:
        if not block_html: return []
        out = []
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
            label = html_lib.unescape(self._plain(a.group(2)))
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
                    tag = re.sub(r'(?is)alt=["\'][^"\']*["\']', f'alt="{self._esc(alt)}"', tag, count=1)
                else:
                    tag = tag[:-1] + f' alt="{self._esc(alt)}"' + tag[-1:]
                return tag
            return re.sub(r'(?is)<img[^>]*>', repl_img, block, count=1)

        pat = rf'(?is)(<div\s+id=["\']{re.escape(div_id)}["\'][^>]*>)(.*?)(</div\s*>)'
        if re.search(pat, html):
            return re.sub(pat, lambda m: m.group(1) + replace_first_img(m.group(2)) + m.group(3), html, count=1)
        # If no existing div, create new
        img_html = f'<div class="lightbox-container">\n  <img src="{self._esc(prefix + filename)}" class="zoomable" alt="{self._esc(alt)}" onclick="openLightbox(this)">\n</div>'
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

    def _set_meta_keywords(self, html: str, kw: str) -> str:
        if not kw:
            return html
        if re.search(r'(?is)<meta[^>]+name=["\']keywords["\']', html):
            return re.sub(r'(?is)(<meta[^>]+name=["\']keywords["\'][^>]+content=["\']).*?(["\'])',
                          r'\1' + self._esc(kw) + r'\2', html, count=1)
        return re.sub(r'(?is)</head>', f'<meta name="keywords" content="{self._esc(kw)}">\n</head>', html, count=1)

    def _plain(self, html: str) -> str:
        return re.sub(r"<[^>]+>", "", html).strip()
    def _esc(self, s: str) -> str:
        return (s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))

# ---------- Main Window ----------
class StudioWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME); self.resize(1400, 860)
        self.project_root: Optional[Path] = None
        self.cfg: Optional[ConfigService] = None
        self.stats: Optional[StatsService] = None
        self.htmlsvc: Optional[HtmlService] = None
        self.tpl: Optional[TemplateService] = None
        self.filesvc: Optional[FileService] = None
        self.ai: Optional[AiService] = None

        # AI intent routing
        self._ai_mode: Optional[str] = None  # "keywords" or section name

        self._build_ui()
        self._apply_theme()
        self._attach_default_tree_model()
        last_guess = Path.home() / "minipcb.github.io"
        self.open_project_dialog(initial=last_guess if last_guess.exists() else None)

    def _build_ui(self):
        menubar=self.menuBar()
        filem=menubar.addMenu("&File")
        self.open_act=QtWidgets.QAction("Open Project…", self)
        self.save_act=QtWidgets.QAction("Save Current Tab", self); self.save_act.setShortcut(QtGui.QKeySequence("Ctrl+S"))
        filem.addAction(self.open_act); filem.addAction(self.save_act); filem.addSeparator()
        self.export_stats_act=QtWidgets.QAction("Export AI Usage CSV…", self); filem.addAction(self.export_stats_act)
        filem.addSeparator()
        self.exit_act=QtWidgets.QAction("E&xit", self); filem.addAction(self.exit_act)

        newm=menubar.addMenu("&New")
        self.new_board_act=QtWidgets.QAction("Board Page", self)
        self.new_collection_act=QtWidgets.QAction("Collection Page", self)
        newm.addAction(self.new_board_act); newm.addAction(self.new_collection_act)

        aim=menubar.addMenu("&AI")
        self.ai_section_combo=QtWidgets.QComboBox(); self.ai_section_combo.addItems(HTML_ANALYSIS_BLOCKS_MENU)
        self.ai_context_act=QtWidgets.QAction("Generate Selected Section…", self)
        aiw=QtWidgets.QWidget(); hl=QtWidgets.QHBoxLayout(aiw); hl.setContentsMargins(6,2,6,2)
        hl.addWidget(QtWidgets.QLabel("Section:")); hl.addWidget(self.ai_section_combo)
        corner=QtWidgets.QWidgetAction(self); corner.setDefaultWidget(aiw)
        aim.addAction(self.ai_context_act); aim.addAction(corner)

        self.tree=QtWidgets.QTreeView(); self.tree.setHeaderHidden(True); self.tree.setMinimumWidth(280)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree_menu=QtWidgets.QMenu(self); self.tree_new_folder=self.tree_menu.addAction("New Folder…")
        self.tree_rename=self.tree_menu.addAction("Rename…"); self.tree_move=self.tree_menu.addAction("Move to…")
        self.tree_delete=self.tree_menu.addAction("Delete")

        self.tabs=QtWidgets.QTabWidget(); self.tabs.setTabsClosable(True); self.tabs.setMovable(True); self.tabs.tabCloseRequested.connect(self._close_tab)

        # Board Forms dock
        self.forms_dock=QtWidgets.QDockWidget("Board Forms", self)
        self.forms_dock.setAllowedAreas(QtCore.Qt.RightDockWidgetArea); self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.forms_dock)
        self.forms: Optional[BoardForms] = None

        # Splitter
        split=QtWidgets.QSplitter(); split.addWidget(self.tree); split.addWidget(self.tabs)
        split.setStretchFactor(0,0); split.setStretchFactor(1,1); split.setSizes([320, 1080])
        self.setCentralWidget(split)

        self.status=self.statusBar()

        # connections
        self.open_act.triggered.connect(lambda: self.open_project_dialog())
        self.exit_act.triggered.connect(self.close)
        self.save_act.triggered.connect(self._save_current_tab)
        self.export_stats_act.triggered.connect(self._export_stats)
        self.new_board_act.triggered.connect(self._new_board)
        self.new_collection_act.triggered.connect(self._new_collection)
        self.ai_context_act.triggered.connect(self._ai_generate_menu)

        self.tree.customContextMenuRequested.connect(self._tree_context)
        self.tree.doubleClicked.connect(self._tree_open)
        self.tree_new_folder.triggered.connect(self._tree_new_folder)
        self.tree_rename.triggered.connect(self._tree_rename)
        self.tree_move.triggered.connect(self._tree_move)
        self.tree_delete.triggered.connect(self._tree_delete)

    def _apply_theme(self):
        QtWidgets.qApp.setStyle("Fusion")
        self.setStyleSheet(DARK_QSS)

    def _attach_default_tree_model(self):
        model=QtWidgets.QFileSystemModel()
        home=str(Path.home()); model.setRootPath(home)
        model.setNameFilters(["*.html","*.md","*.pdf","*.png","*.jpg","*.jpeg","*.svg","*.css","*.js"])
        model.setNameFilterDisables(False)
        self.tree.setModel(model); self.tree.setRootIndex(model.index(home))

    # ---- Project lifecycle
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
        self.status.showMessage(f"Opened project: {root}", 4000)

        # Build forms dock now that we have root/htmlsvc
        self.forms = BoardForms(root, self.htmlsvc)
        self.forms.request_generate_keywords.connect(self._ai_keywords)
        self.forms.request_generate_description.connect(self._ai_description)
        self.forms.apply_btn.clicked.connect(self._forms_apply_to_html)
        self.forms.reload_btn.clicked.connect(self._forms_reload_from_html)
        self.forms_dock.setWidget(self.forms.container)

        # AI signals
        self.ai.finished.connect(self._ai_finished)
        self.ai.failed.connect(self._ai_failed)

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
        p=self._index_to_path(idx); 
        if p: self._open_path(p)

    # ---- Tabs / open/save
    def _open_path(self, p: Path):
        # activate if open
        for i in range(self.tabs.count()):
            if getattr(self.tabs.widget(i), "path", None)==p:
                self.tabs.setCurrentIndex(i); return
        if p.suffix.lower()==".pdf":
            tab=PdfViewerTab(p); self.tabs.addTab(tab, f"PDF: {p.name}"); self.tabs.setCurrentWidget(tab); return
        if p.suffix.lower() in (".png",".jpg",".jpeg",".svg"):
            tab=ImageViewerTab(p); self.tabs.addTab(tab, f"IMG: {p.name}"); self.tabs.setCurrentWidget(tab); return
        if p.suffix.lower()==".html":
            tab=HtmlEditorTab(p, self.htmlsvc); tab.content_changed.connect(lambda: self._tab_dirty(tab,True))
            self.tabs.addTab(tab, f"HTML: {p.name}"); self.tabs.setCurrentWidget(tab)
            # Load forms if board page
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
        tab=TextViewerTab(p, editable=True); tab.content_changed.connect(lambda: self._tab_dirty(tab,True))
        self.tabs.addTab(tab, f"TXT: {p.name}"); self.tabs.setCurrentWidget(tab)
        self.forms_dock.setVisible(False)

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

    def _save_current_tab(self):
        w=self.tabs.currentWidget()
        if w: self._save_tab(w)
    def _save_tab(self, tab: QtWidgets.QWidget):
        if isinstance(tab, HtmlEditorTab):
            self.filesvc.write_text(tab.path, tab.text(), backup=True); self._tab_dirty(tab,False); self.status.showMessage(f"Saved {tab.path.name}", 3000)
        elif isinstance(tab, TextViewerTab):
            self.filesvc.write_text(tab.path, tab.text(), backup=True); self._tab_dirty(tab,False); self.status.showMessage(f"Saved {tab.path.name}", 3000)
    def _tab_dirty(self, tab: QtWidgets.QWidget, on: bool):
        i=self.tabs.indexOf(tab); 
        if i<0: return
        t=self.tabs.tabText(i)
        if on and not t.endswith(" •"): self.tabs.setTabText(i, t+" •")
        if not on and t.endswith(" •"): self.tabs.setTabText(i, t[:-2])

    # ---- Create new pages
    def _new_board(self):
        if not self.project_root: QtWidgets.QMessageBox.information(self,"Open project","Open a project first."); return
        name,ok=QtWidgets.QInputDialog.getText(self,"New Board Page","Filename (e.g., 04B-350.html):")
        if not (ok and name.strip()): return
        p=self.project_root / name.strip()
        if p.exists(): QtWidgets.QMessageBox.warning(self,"Exists","File already exists."); return
        imgs_dir=self.cfg.get("images_dir","images"); s,l = guess_images(self.project_root / imgs_dir)
        html=self.tpl.new_board("XX-000","Board Title","", "miniPCB, board", s, l)
        self.filesvc.write_text(p, html, backup=False); self._open_path(p)

    def _new_collection(self):
        if not self.project_root: QtWidgets.QMessageBox.information(self,"Open project","Open a project first."); return
        name,ok=QtWidgets.QInputDialog.getText(self,"New Collection Page","Filename (e.g., transistor-amplifiers.html):")
        if not (ok and name.strip()): return
        p=self.project_root / name.strip()
        if p.exists(): QtWidgets.QMessageBox.warning(self,"Exists","File already exists."); return
        html=self.tpl.new_collection("Collection","A collection of boards.","miniPCB, collection")
        self.filesvc.write_text(p, html, backup=False); self._open_path(p)

    # ---- Forms <-> HTML
    def _forms_reload_from_html(self):
        tab = self.tabs.currentWidget()
        if not isinstance(tab, HtmlEditorTab): return
        self.forms.load_from_html(tab.text(), tab.path)

    def _forms_apply_to_html(self):
        tab = self.tabs.currentWidget()
        if not isinstance(tab, HtmlEditorTab): return
        before = tab.text()
        text = self.forms.apply_to_html(before)
        # Update meta description from first human bullet (if any)
        bullets = [x.strip() for x in self.forms.m_desc_list.toPlainText().splitlines() if x.strip()]
        if bullets:
            text = self.htmlsvc.set_meta(text, desc=bullets[0], keywords=None)
        self._apply_via_diff(tab, before, text)

    def _apply_via_diff(self, tab: HtmlEditorTab, before: str, after: str):
        diff="\n".join(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile="before", tofile="after", lineterm=""))
        dlg=QtWidgets.QDialog(self); dlg.setWindowTitle("Preview Diff"); dlg.resize(960,640)
        v=QtWidgets.QVBoxLayout(dlg); e=QtWidgets.QPlainTextEdit(); e.setReadOnly(True); e.setPlainText(diff or "(No changes)")
        v.addWidget(e,1); bb=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Save); v.addWidget(bb)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        if dlg.exec_()==QtWidgets.QDialog.Accepted:
            tab.set_text(after); self._tab_dirty(tab, True); self.status.showMessage("Forms applied to editor (unsaved).", 4000)

    # ---- AI actions
    def _ai_generate_menu(self):
        tab=self.tabs.currentWidget()
        if not isinstance(tab, HtmlEditorTab): 
            QtWidgets.QMessageBox.information(self,"Not HTML","Open an HTML page first."); return
        section=self.ai_section_combo.currentText()
        self._ai_mode = section  # route on finish
        title = self.forms.m_title.text().strip() if self.forms else self._safe_title(tab.text())
        keywords = self.forms.m_keywords.toPlainText().replace("\n"," ").strip() if self.forms else ""
        maturity = self.forms.d_maturity.currentIndex() if self.forms else 1
        seed = self.forms.d_seed.toPlainText().strip() if self.forms else ""
        self.status.showMessage(f"AI: generating {section}…", 2000)
        self.ai.generate_async(section, title, keywords, maturity, seed, tab.path)

    def _ai_keywords(self):
        tab=self.tabs.currentWidget()
        if not isinstance(tab, HtmlEditorTab): 
            QtWidgets.QMessageBox.information(self,"Not HTML","Open an HTML page first."); return
        title = self.forms.m_title.text().strip()
        bullets = self.forms.m_desc_list.toPlainText().strip()
        seed = f"Generate a concise, comma-separated keyword list for site search.\nTitle: {title}\nNotes:\n{bullets}\n"
        self._ai_mode = "keywords"
        self.ai.generate_async("KEYWORDS", title, "", 1, seed, tab.path)

    def _ai_description(self):
        tab=self.tabs.currentWidget()
        if not isinstance(tab, HtmlEditorTab): 
            QtWidgets.QMessageBox.information(self,"Not HTML","Open an HTML page first."); return
        self._ai_mode = "DESCRIPTION"
        title = self.forms.m_title.text().strip()
        keywords = self.forms.m_keywords.toPlainText().replace("\n"," ").strip()
        maturity = self.forms.d_maturity.currentIndex()
        seed = self.forms.d_seed.toPlainText().strip()
        self.status.showMessage("AI: generating Description…", 2000)
        self.ai.generate_async("DESCRIPTION", title, keywords, maturity, seed, tab.path)

    def _ai_failed(self, msg: str):
        QtWidgets.QMessageBox.critical(self,"AI Error", msg)

    def _ai_finished(self, section: str, html_fragment: str):
        tab=self.tabs.currentWidget()
        if not isinstance(tab, HtmlEditorTab): return

        # Update statusbar stats
        if self.stats:
            self.status.showMessage(f"AI events: {self.stats.session_events}  In: {self._fmt_bytes(self.stats.session_in)}  Out: {self._fmt_bytes(self.stats.session_out)}", 5000)

        # Route by mode
        mode = self._ai_mode or section
        if mode == "keywords":
            txt = re.sub(r"<[^>]+>","", html_fragment).strip()
            if self.forms: self.forms.m_keywords.setPlainText(txt.replace("\n"," ").strip())
            self.status.showMessage("AI keywords populated (review before applying).", 4000)
            return

        # For DESCRIPTION: merge into #description .generated
        if mode == "DESCRIPTION":
            current = tab.text()
            # replace only the generated block
            def repl_gen(m):
                block = m.group(0)
                block = re.sub(r'(?is)(<div\s+class=["\']generated["\'][^>]*>).*?(</div>)',
                               r'\1' + html_fragment.strip() + r'\2', block, count=1)
                return block
            merged = re.sub(r'(?is)<div\s+id=["\']description["\'][^>]*>.*?</div\s*>', repl_gen, current, count=1)
            if merged == current:
                # if #description missing, create it
                merged = self.forms._set_div_inner(current, "description",
                    "<h2>Description</h2>\n<h3>AI Seed</h3>\n<p></p>\n<h3>AI Generated</h3>\n<div class=\"generated\">\n" + html_fragment.strip() + "\n</div>")
            self._apply_via_diff(tab, current, merged)
            return

        # Other sections: create/update a hidden div with id=lowercase section name
        sec_id = mode.lower()
        current = tab.text()
        content = "<div class=\"generated\">\n" + html_fragment.strip() + "\n</div>"
        merged = self.forms._set_div_inner(current, sec_id, f"<h2>{mode.title()}</h2>\n{content}")
        self._apply_via_diff(tab, current, merged)

    def _safe_title(self, text: str) -> str:
        m=re.search(r"(?is)<title>(.*?)</title>", text); return (m.group(1).strip() if m else "Untitled")

    # ---- Stats
    def _fmt_bytes(self, n:int)->str:
        for unit in ["B","KB","MB","GB"]:
            if n<1024.0: return f"{n:.0f} {unit}"
            n/=1024.0
        return f"{n:.1f} TB"

    def _export_stats(self):
        if not self.stats: return
        out, _ = QtWidgets.QFileDialog.getSaveFileName(self,"Export AI Usage CSV", str((self.project_root or Path.home())/"ai_usage.csv"), "CSV (*.csv)")
        if not out: return
        self.stats.export_csv(Path(out)); self.status.showMessage(f"Exported stats to {out}", 4000)

# ---------- Entry ----------
def main():
    # HiDPI & pixmaps before QApplication
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
