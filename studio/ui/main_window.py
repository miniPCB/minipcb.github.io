import os
import json, re
import time
from pathlib import Path
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QMessageBox

from pathlib import Path
from PyQt5.QtWidgets import (
    QMainWindow, QSplitter, QStatusBar, QLabel, QFileDialog, QMessageBox,
    QAction, QInputDialog, QTabWidget, QAction, QMessageBox, QDialog, QVBoxLayout,
    QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton
)

from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QKeySequence
from .left_tree import FolderTree
from .editor_panel import EditorPanel
from .settings_dialog import SettingsDialog
from app.autosave import AutoSaver
from app.hotkeys import install_hotkeys
from services.batch_ops import BatchOps
from services.file_service import FileService
from services.template_loader import Templates
from services.html_service import HtmlService
from services.ai_service import AIService
from .tabs.main_tabs import MainTabs

from typing import Any, Dict, List, Optional, Tuple


class AIProgressDialog(QDialog):
    def __init__(self, parent=None, eta_sec=None):
        super().__init__(parent)
        self.setWindowTitle("Generating with AI…")
        self.setModal(True)
        self._t0 = time.time()
        self._eta = eta_sec
        self._lbl = QLabel(self)
        self._lbl.setText("Starting…")
        self._lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel, self)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(self._lbl)
        lay.addWidget(btns)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        elapsed = time.time() - self._t0
        if self._eta and self._eta > 0:
            remain = max(0, self._eta - elapsed)
            self._lbl.setText(f"Working…  elapsed {elapsed:0.1f}s   ETA ~{remain:0.1f}s")
        else:
            self._lbl.setText(f"Working…  elapsed {elapsed:0.1f}s")

    def finish_ok(self):
        self._timer.stop()
        self.accept()

    def finish_error(self, message: str):
        self._timer.stop()
        QMessageBox.critical(self, "AI Error", message)
        self.reject()

class AIGenWorker(QThread):
    done = pyqtSignal(object)   # AIResult
    fail = pyqtSignal(str)

    def __init__(self, project_root: Path, html: str, seeds: dict, parent=None):
        super().__init__(parent)
        self.project_root = Path(project_root)
        self.html = html
        self.seeds = seeds

    def run(self):
        try:
            from services.ai_service import AIService
            svc = AIService(self.project_root)
            res = svc.generate_description(self.html, self.seeds)
            self.done.emit(res)
        except Exception as e:
            self.fail.emit(str(e))

class AISeedsDialog(QDialog):
    def __init__(self, parent=None, seeds=None):
        super().__init__(parent)
        self.setWindowTitle("Edit AI Seeds")
        self.setModal(True)
        self.resize(720, 540)

        seeds = seeds or {}
        # Normalize legacy structure -> single testing_seed
        testing_seed = seeds.get("testing_seed", "")
        if not testing_seed and isinstance(seeds.get("testing"), dict):
            dtp = (seeds["testing"].get("dtp_seed") or "").strip()
            atp = (seeds["testing"].get("atp_seed") or "").strip()
            merged = "\n".join([s for s in (dtp, atp) if s]).strip()
            testing_seed = merged

        layout = QVBoxLayout(self)

        # Description seed
        layout.addWidget(QLabel("Description Seed:"))
        self.txt_desc = QPlainTextEdit()
        self.txt_desc.setPlainText(seeds.get("description_seed", ""))
        self.txt_desc.setTabChangesFocus(True)
        layout.addWidget(self.txt_desc, 1)

        # Testing seed (single)
        layout.addWidget(QLabel("Testing Seed:"))
        self.txt_test = QPlainTextEdit()
        self.txt_test.setPlainText(testing_seed)
        self.txt_test.setTabChangesFocus(True)
        layout.addWidget(self.txt_test, 1)

        # FMEA seed
        layout.addWidget(QLabel("FMEA Seed:"))
        self.txt_fmea = QPlainTextEdit()
        self.txt_fmea.setPlainText(seeds.get("fmea_seed", ""))
        self.txt_fmea.setTabChangesFocus(True)
        layout.addWidget(self.txt_fmea, 1)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def result_seeds(self):
        # Always write a flat structure: description_seed, testing_seed, fmea_seed
        return {
            "description_seed": self.txt_desc.toPlainText().strip(),
            "testing_seed": self.txt_test.toPlainText().strip(),
            "fmea_seed": self.txt_fmea.toPlainText().strip(),
        }
    
class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("miniPCB Studio")
        self.resize(1400, 900)

        self.tree = FolderTree(self.ctx)
        self.editor = EditorPanel(self.ctx)
        self.fs = FileService(self.ctx.project_root)
        self.ai = AIService(self.ctx.project_root)

        splitter = QSplitter(self)
        splitter.addWidget(self.tree)

        # Right side has two major tabs: Forms and Raw Text
        self.right_tabs = QTabWidget(self)
        self.tabs_view = MainTabs(self.ctx, get_editor_text_callable=lambda: self.editor.edit.toPlainText())
        self.right_tabs.addTab(self.tabs_view, "Forms")
        self.right_tabs.addTab(self.editor, "Raw Text")
        splitter.addWidget(self.right_tabs)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.autosave_label = QLabel("Autosave ready", self)
        self.status.addPermanentWidget(self.autosave_label)

        # remember last active major tab (Forms/Raw Text) per file type
        self._last_tab_for_type = {'board': 0, 'collection': 0, 'other': 0}

        # wires
        self.tree.fileSelected.connect(self._on_file_selected)
        self.editor.pathLoaded.connect(self._on_editor_path_loaded)

        # track UI tab/type changes
        self.right_tabs.currentChanged.connect(self._on_right_tab_changed)
        self.tabs_view.typeChanged.connect(self._on_tabs_type_changed)

        # autosave
        self.autosaver = AutoSaver(self.ctx.settings.get("autosave_seconds", 30), self)
        self.autosaver.tick.connect(self._on_autosave_tick)
        self.autosaver.trigger_save.connect(self.handle_save_current)
        self.autosaver.start()
        self.editor.dirtyChanged.connect(self.autosaver.set_dirty)

        # menus
        self._build_menus()
        install_hotkeys(self)  # keep other hotkeys; Ctrl+S is handled below

        # restore last opened folder/file
        self._restore_last_opened()
        self._apply_last_tab_for_type()

    # ---------------- Menus ----------------
    def _build_menus(self):
        mb = self.menuBar()

        # File
        m_file = mb.addMenu("&File")
        act_new_file = QAction("New File…", self, triggered=self._new_file)
        act_new_folder = QAction("New Folder…", self, triggered=self._new_folder)
        act_rename = QAction("Rename…", self, triggered=self._rename_selected)
        act_delete = QAction("Delete…", self, triggered=self._delete_selected)

        # IMPORTANT: do not assign Ctrl+S here (we handle it in keyPressEvent to avoid ambiguity)
        act_save = QAction("Save", self, triggered=self.handle_save_current)

        act_update_html = QAction("Update HTML (This File)", self, triggered=self._update_html_current)
        act_update_all = QAction("Update All HTML…", self, triggered=self.handle_update_all_html)
        act_open_folder = QAction("Open Root Folder…", self, triggered=self._open_root_folder_dialog)
        act_exit = QAction("Exit", self, triggered=self.close)
        for a in (
            act_new_file, act_new_folder, act_rename, act_delete,
            None, act_save, act_update_html, act_update_all,
            None, act_open_folder, act_exit
        ):
            if a is None:
                m_file.addSeparator()
            else:
                m_file.addAction(a)

        # Settings
        m_settings = mb.addMenu("&Settings")
        act_settings = QAction("Preferences…", self, triggered=self._open_settings)
        m_settings.addAction(act_settings)

        # AI Tools
        m_ai = mb.addMenu("&AI Tools")

        act_ai_desc = QAction("Generate Description", self, triggered=self._ai_generate_description)
        act_ai_fmea = QAction("Generate FMEA Rows", self, triggered=self._ai_generate_fmea)
        act_ai_test = QAction("Generate Testing Rows", self, triggered=self._ai_generate_testing)
        m_ai.addAction(act_ai_desc)
        m_ai.addAction(act_ai_fmea)
        m_ai.addAction(act_ai_test)

        m_ai.addSeparator()
        act_ai_edit_seeds = QAction("Edit AI Seeds…", self, triggered=self._ai_edit_seeds)
        m_ai.addAction(act_ai_edit_seeds)

        # Help
        m_help = mb.addMenu("&Help")
        act_about = QAction("About", self, triggered=lambda: QMessageBox.information(self, "About", "miniPCB Studio — Website Manager"))
        m_help.addAction(act_about)

    # Global key handling for Ctrl+S (prevents ambiguous shortcut warnings)
    def keyPressEvent(self, event):
        if (event.modifiers() & Qt.ControlModifier) and event.key() in (Qt.Key_S,):
            self.handle_save_current()
            event.accept()
            return
        super().keyPressEvent(event)

    # ---------------- AI Actions ----------------
    def _ai_generate_description(self):
        """
        - Reads current HTML + AI seeds from the editor/tabs
        - Shows progress dialog with ETA from history
        - Writes AI text back into the Description field (not HTML yet; your autosync handles it)
        - Logs usage to .minipcb_ai/ai_usage.jsonl
        """
        tabs = self._get_main_tabs()
        if not tabs:
            QMessageBox.information(self, "AI", "Open a board HTML first.")
            return

        # Get current HTML from the right editor via the tabs helper
        getter = getattr(tabs, "get_editor_text", None)
        html = getter() if callable(getter) else ""
        if not html.strip():
            QMessageBox.information(self, "AI", "No HTML loaded.")
            return

        # Read seeds from HTML
        seeds = {}
        if hasattr(tabs, "_read_ai_seeds_from_html"):
            seeds = tabs._read_ai_seeds_from_html(html)

        # Rough ETA from prior runs
        try:
            from services.ai_service import AIService
            svc = AIService(self.ctx.project_root)
            eta = svc.historical_eta_sec("description")
        except Exception:
            eta = None

        prog = AIProgressDialog(self, eta_sec=eta)
        # Run worker
        worker = AIGenWorker(self.ctx.project_root, html, seeds, parent=self)
        # Keep refs alive
        self._ai_prog = prog
        self._ai_worker = worker

        def _on_done(res):
            # Close dialog first
            prog.finish_ok()

            if not res.ok and res.error:
                QMessageBox.warning(self, "AI", f"Completed with fallback: {res.error}")

            # Put result into Description form field
            if hasattr(tabs, "txt_description"):
                tabs.txt_description.setPlainText(res.text)
                # schedule a sync back to HTML (your debounced sync already does the rest)
                if hasattr(tabs, "_schedule_sync"):
                    tabs._schedule_sync()

            # Optional: quick toast
            QMessageBox.information(
                self, "AI",
                f"Description generated.\nTime: {res.ended_at - res.started_at:0.2f}s\n"
                f"~Tokens prompt/resp: {res.prompt_tokens_est}/{res.response_tokens_est}"
            )

            # Cleanup refs
            self._ai_worker = None
            self._ai_prog = None

        def _on_fail(msg):
            prog.finish_error(msg)
            self._ai_worker = None
            self._ai_prog = None

        worker.done.connect(_on_done)
        worker.fail.connect(_on_fail)
        worker.start()
        prog.exec_()

    def _ai_generate_fmea(self):
        cur = self.editor.current_path()
        if not cur:
            QMessageBox.information(self, "AI", "Open a file first.")
            return
        try:
            rows = self.ai.generate_fmea(str(cur))
            headers = [
                "Item","Potential Failure Mode","Potential Effect of Failure","Severity",
                "Potential Causes/Mechanisms","Occurrence","Current Process Controls","Detection",
                "RPN","Recommended Actions","Responsibility","Target Completion Date",
                "Actions Taken","Resulting Severity","Resulting Occurrence","Resulting Detection","New RPN"
            ]
            md = [
                "", "### FMEA (AI)", "",
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join(["---"] * len(headers)) + " |"
            ]
            for r in rows:
                md.append("| " + " | ".join(str(x) for x in r) + " |")
            new_block = "\n".join(md) + "\n"
            self.editor.set_text(self.editor.edit.toPlainText() + "\n" + new_block)
            self.status.showMessage("AI FMEA rows appended", 3000)
        except Exception as e:
            QMessageBox.critical(self, "AI Error", str(e))

    def _ai_generate_testing(self):
        # 1) Get current HTML from the editor (string, not a path)
        html = ""
        try:
            # Prefer an explicit getter if your editor provides one
            if hasattr(self.editor, "get_text"):
                html = self.editor.get_text() or ""
            else:
                # fallback if the editor exposes the widget
                html = self.editor.edit.toPlainText()
        except Exception:
            pass
        if not html.strip():
            QMessageBox.information(self, "AI", "Open a file first.")
            return

        # 2) Extract seeds from the page (supports both new 'testing_seed' and old nested 'testing')
        seeds = self._extract_ai_seeds_from_html(html)

        # 3) Call the AI service with *html* and *seeds*
        try:
            res = self.ai.generate_testing(html, seeds)
        except Exception as e:
            QMessageBox.critical(self, "AI Error", str(e))
            return

        # 4) Show errors but still use fallback text if provided
        if not res.ok and res.error:
            self.status.showMessage(f"AI warning: {res.error}", 5000)

        # 5) Append a small markdown block so you can see what came back (optional)
        #    If you instead want to push rows into the Testing table UI, do that here.
        headers = ["Test No.","Test Name","Test Description","Lower Limit","Target Value","Upper Limit","Units"]
        md = [
            "", "### Testing (AI)", "",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |"
        ]
        # Split CSV lines safely (handles commas inside quotes)
        import re as _re
        def _csv_split(line: str):
            parts = [_p.strip() for _p in _re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', line)]
            # strip surrounding quotes
            clean = []
            for p in parts:
                if len(p) >= 2 and p[0] == p[-1] == '"':
                    clean.append(p[1:-1])
                else:
                    clean.append(p)
            # pad/crop to 7 fields
            clean = (clean + [""] * 7)[:7]
            return clean

        for line in (res.text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            cols = _csv_split(line)
            md.append("| " + " | ".join(cols) + " |")

        self.editor.set_text(self.editor.edit.toPlainText() + "\n" + "\n".join(md) + "\n")
        self.status.showMessage("AI Testing rows appended", 3000)

    # ---------------- File Actions ----------------
    def handle_save_current(self):
        if self.editor.save_current():
            self.status.showMessage("Saved", 2000)

    def handle_update_all_html(self):
        root = QFileDialog.getExistingDirectory(self, "Choose site root", str(self.ctx.project_root))
        if not root:
            return
        ops = BatchOps(Path(root), self.ctx.templates_dir)
        try:
            ops.update_all_html()
            QMessageBox.information(self, "Update All", "All HTML files updated to latest template.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _update_html_current(self):
        cur = self.editor.current_path()
        if not cur or not str(cur).lower().endswith(".html"):
            QMessageBox.information(self, "Update HTML", "Open an HTML file first.")
            return
        try:
            html = cur.read_text(encoding="utf-8")
            templates = Templates(self.ctx.templates_dir)
            htmlsvc = HtmlService(templates)
            data = htmlsvc.extract_metadata(html)
            new_shell = htmlsvc.build_new_shell({
                "TITLE": data.get("title",""),
                "PN": data.get("pn",""),
                "SLOGAN": data.get("seo",{}).get("slogan",""),
                "KEYWORDS": ",".join(data.get("seo",{}).get("keywords",[])),
                "DESCRIPTION": data.get("seo",{}).get("description",""),
            })
            merged = htmlsvc.apply_metadata(new_shell, data)
            cur.write_text(merged, encoding="utf-8")
            self.editor.set_text(merged)
            self.status.showMessage("Updated HTML using latest template", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Update HTML Error", str(e))

    def _new_file(self):
        root = self._current_root()
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if not ok or not name.strip():
            return
        p = Path(root) / name.strip()
        if p.exists():
            QMessageBox.warning(self, "Exists", "File already exists.")
            return
        p.write_text("", encoding="utf-8")
        self.status.showMessage(f"Created {p}", 2000)

    def _new_folder(self):
        root = self._current_root()
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok or not name.strip():
            return
        p = Path(root) / name.strip()
        if p.exists():
            QMessageBox.warning(self, "Exists", "Folder already exists.")
            return
        p.mkdir(parents=True, exist_ok=False)
        self.status.showMessage(f"Created folder {p}", 2000)

    def _rename_selected(self):
        idx = self.tree.view.currentIndex()
        if not idx.isValid():
            return
        path = Path(self.tree.model.filePath(idx))
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=path.name)
        if not ok or not new_name.strip():
            return
        dst = path.with_name(new_name.strip())
        try:
            os.replace(path, dst)
            self.status.showMessage(f"Renamed to {dst.name}", 2000)
        except Exception as e:
            QMessageBox.critical(self, "Rename Error", str(e))

    def _delete_selected(self):
        idx = self.tree.view.currentIndex()
        if not idx.isValid():
            return
        path = Path(self.tree.model.filePath(idx))
        if QMessageBox.question(self, "Delete", f"Delete '{path.name}'?") != QMessageBox.Yes:
            return
        try:
            if path.is_dir():
                import shutil
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            self.status.showMessage("Deleted", 2000)
        except Exception as e:
            QMessageBox.critical(self, "Delete Error", str(e))

    def _open_root_folder_dialog(self):
        path = QFileDialog.getExistingDirectory(self, "Open Root Folder", str(self.ctx.project_root))
        if path:
            self._set_root(Path(path))

    # ---------------- Settings ----------------
    def _open_settings(self):
        dlg = SettingsDialog(self.ctx, self)
        if dlg.exec_() == dlg.Accepted:
            vals = dlg.values()
            # update settings
            self.ctx.settings.set("templates_dir", str(vals["templates_dir"]))
            self.ctx.settings.set("images_dir", str(vals["images_dir"]))
            self.ctx.settings.set("autosave_seconds", vals["autosave_seconds"])
            # change root folder if different
            if Path(vals["project_root"]) != self.ctx.project_root:
                self._set_root(Path(vals["project_root"]))

    def _set_root(self, path: Path):
        self.ctx.project_root = Path(path)
        self.ctx.settings.set("last_open_folder", str(path))
        self.tree.set_root(path)
        self.fs = FileService(self.ctx.project_root)
        self.status.showMessage(f"Root set to: {path}", 3000)

    def _restore_last_opened(self):
        # Restore last folder
        try:
            last_folder = Path(self.ctx.settings.get("last_open_folder", str(self.ctx.project_root)))
            if last_folder.exists():
                self._set_root(last_folder)
        except Exception:
            pass
        # Restore last file
        try:
            last_file = self.ctx.settings.get("last_open_file", "")
            if last_file:
                p = Path(last_file)
                if p.exists() and p.is_file():
                    self.editor.load_path(str(p))
                    try:
                        self.tabs_view.load_html_file(p)
                    except Exception:
                        pass
        except Exception:
            pass

    # ---------------- Helpers ----------------
    def _current_root(self) -> Path:
        return self.ctx.project_root

    def _on_file_selected(self, path: str):
        self.editor.load_path(path)
        try:
            p = Path(path)
            self.tabs_view.load_html_file(p)
            self._apply_last_tab_for_type()
        except Exception:
            pass

    def _on_editor_path_loaded(self, p: Path):
        # Persist last opened file & folder
        try:
            self.ctx.settings.set("last_open_file", str(p))
            self.ctx.settings.set("last_open_folder", str(p.parent))
        except Exception:
            pass

    # ---- Remember last active major tab per file type ----
    def _apply_last_tab_for_type(self):
        ftype = getattr(self.tabs_view, 'current_type', 'other')
        idx = self._last_tab_for_type.get(ftype, 0)
        if 0 <= idx < self.right_tabs.count():
            self.right_tabs.setCurrentIndex(idx)

    def _on_right_tab_changed(self, index: int):
        ftype = getattr(self.tabs_view, 'current_type', 'other')
        self._last_tab_for_type[ftype] = index

    def _on_tabs_type_changed(self, ftype: str):
        self._apply_last_tab_for_type()

    def _on_autosave_tick(self, remaining: int):
        if remaining > 0 and self.editor.is_dirty():
            self.autosave_label.setText(f"Autosave in {remaining}s")
        else:
            self.autosave_label.setText("Saved")

    def _get_main_tabs(self):
        # Find the MainTabs instance (left pane).
        from ui.tabs.main_tabs import MainTabs
        tabs = self.findChild(MainTabs)
        return tabs

    def _menu_edit_ai_seeds(self):
        tabs = self._get_main_tabs()
        if tabs:
            tabs._on_edit_ai_seeds()

    def _menu_generate_description_ai(self):
        # Minimal stub – you can later call your AI service here
        try:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "AI", "Stub: Generate Description via AI.\n(Connect to your AI service here.)")
        except Exception:
            pass

    def _ai_edit_seeds(self):
        """Open the AI Seeds editor on the active MainTabs pane."""
        try:
            # Local import avoids circulars
            from ui.tabs.main_tabs import MainTabs
            tabs = self.findChild(MainTabs)
            if tabs and hasattr(tabs, "_on_edit_ai_seeds"):
                tabs._on_edit_ai_seeds()
            else:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.information(self, "Edit AI Seeds", "Open a board HTML first, then try again.")
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Edit AI Seeds", f"Could not open AI Seeds editor:\n{e}")

    def _extract_ai_seeds_from_html(self, html: str) -> Dict[str, Any]:
        """
        Pulls JSON from:
        <div id="ai-seeds"> <script id="ai-seeds-json" type="application/json">{...}</script> </div>
        Returns {} if not present or invalid.
        """
        try:
            m = re.search(r'(?is)<script[^>]+id=["\']ai-seeds-json["\'][^>]*>(.*?)</script>', html)
            if not m:
                return {}
            raw = m.group(1).strip()
            data = json.loads(raw)

            # Normalize: allow either new flat key 'testing_seed' or legacy nested 'testing'
            if "testing_seed" in data and isinstance(data["testing_seed"], str):
                # leave as-is
                pass
            elif "testing" in data and isinstance(data["testing"], dict):
                # collapse legacy dtp/atp into a single testing_seed for AIService
                dtp = (data["testing"].get("dtp_seed") or "").strip()
                atp = (data["testing"].get("atp_seed") or "").strip()
                merged = "\n".join([s for s in (dtp, atp) if s]).strip()
                if merged:
                    data["testing_seed"] = merged
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def parse_ai_seeds_from_html(html: str):
        """Return dict of seeds. Supports legacy testing structure."""
        try:
            m = re.search(r'(?is)<script[^>]+id=["\']ai-seeds-json["\'][^>]*>(.*?)</script>', html)
            if not m:
                return {}
            raw = m.group(1).strip()
            data = json.loads(raw) if raw else {}
            # Normalize legacy testing → testing_seed
            if "testing_seed" not in data and isinstance(data.get("testing"), dict):
                dtp = (data["testing"].get("dtp_seed") or "").strip()
                atp = (data["testing"].get("atp_seed") or "").strip()
                merged = "\n".join([s for s in (dtp, atp) if s]).strip()
                if merged:
                    data["testing_seed"] = merged
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def write_ai_seeds_into_html(html: str, seeds: dict) -> str:
        """
        Upsert a pretty block:

        <div id="ai-seeds" class="tab-content" aria-hidden="true" data-hidden="true">
            <script id="ai-seeds-json" type="application/json">{...}</script>
        </div>

        Writes only description_seed, testing_seed, fmea_seed (no legacy structure).
        """
        seeds_out = {
            "description_seed": seeds.get("description_seed", "").strip(),
            "testing_seed": seeds.get("testing_seed", "").strip(),
            "fmea_seed": seeds.get("fmea_seed", "").strip(),
        }
        json_text = json.dumps(seeds_out, ensure_ascii=False)

        # Build pretty block with indentation based on surrounding area if #ai-seeds exists
        m_div = re.search(r'(?is)(<div\b[^>]*id=["\']ai-seeds["\'][^>]*>)(.*?)(</div>)', html)
        pretty_block = (
            '<div aria-hidden="true" class="tab-content" data-hidden="true" id="ai-seeds">\n'
            '  <script id="ai-seeds-json" type="application/json">'
            f'{json_text}'
            '</script>\n'
            '</div>'
        )

        if m_div:
            # Replace whole <div id="ai-seeds">...</div>
            start, end = m_div.start(), m_div.end()
            # Keep the original leading indentation if any
            line_start = html.rfind("\n", 0, start) + 1
            indent = html[line_start:start]
            pretty_indented = "\n".join(indent + ln if ln else ln for ln in pretty_block.splitlines())
            return html[:start] + pretty_indented + html[end:]

        # If #ai-seeds not present, try to append before </main>, else at end of body
        m_main = re.search(r'(?is)(<main\b[^>]*>)(.*?)(</main>)', html)
        if m_main:
            insert_at = m_main.end(2)
            line_start = html.rfind("\n", 0, insert_at) + 1
            indent = html[line_start:insert_at]
            pretty_indented = "\n" + "\n".join(indent + ln for ln in pretty_block.splitlines()) + "\n" + indent
            return html[:insert_at] + pretty_indented + html[insert_at:]

        m_body = re.search(r'(?is)(<body\b[^>]*>)(.*?)(</body>)', html)
        if m_body:
            insert_at = m_body.end(2)
            return html[:insert_at] + "\n" + pretty_block + "\n" + html[insert_at:]

        # Fallback: just append
        return html + "\n" + pretty_block + "\n"
