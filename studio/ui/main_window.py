import os
from pathlib import Path
from PyQt5.QtWidgets import (
    QMainWindow, QSplitter, QStatusBar, QLabel, QFileDialog, QMessageBox,
    QAction, QInputDialog
)
from PyQt5.QtCore import Qt
from .left_tree import FolderTree
from .editor_panel import EditorPanel
from .pdf_panel import PdfPanel
from .tabs.main_tabs import MainTabs
from .settings_dialog import SettingsDialog
from app.autosave import AutoSaver
from app.hotkeys import install_hotkeys
from services.batch_ops import BatchOps
from services.file_service import FileService
from services.template_loader import Templates
from services.html_service import HtmlService
from services.ai_service import AIService

class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("miniPCB Studio")
        self.resize(1400, 900)

        self.tree = FolderTree(self.ctx)
        self.editor = EditorPanel(self.ctx)
        self.pdf = PdfPanel(self.ctx)
        self.fs = FileService(self.ctx.project_root)
        self.ai = AIService(self.ctx.ai_logger)

        splitter = QSplitter(self)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.editor)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.autosave_label = QLabel("Autosave ready", self)
        self.status.addPermanentWidget(self.autosave_label)

        # wires
        self.tree.fileSelected.connect(self._on_file_selected)
        self.editor.openPdfRequested.connect(self._open_pdf)
        self.editor.pathLoaded.connect(self._on_editor_path_loaded)

        # autosave
        self.autosaver = AutoSaver(self.ctx.settings.get("autosave_seconds", 30), self)
        self.autosaver.tick.connect(self._on_autosave_tick)
        self.autosaver.trigger_save.connect(self.handle_save_current)
        self.autosaver.start()
        self.editor.dirtyChanged.connect(self.autosaver.set_dirty)

        # menus
        self._build_menus()
        install_hotkeys(self)

        # restore last opened folder/file
        self._restore_last_opened()

    # ---------------- Menus ----------------
    def _build_menus(self):
        mb = self.menuBar()

        # File
        m_file = mb.addMenu("&File")
        act_new_file = QAction("New File…", self, triggered=self._new_file)
        act_new_folder = QAction("New Folder…", self, triggered=self._new_folder)
        act_rename = QAction("Rename…", self, triggered=self._rename_selected)
        act_delete = QAction("Delete…", self, triggered=self._delete_selected)
        act_save = QAction("Save", self, shortcut="Ctrl+S", triggered=self.handle_save_current)
        act_update_html = QAction("Update HTML (This File)", self, triggered=self._update_html_current)
        act_update_all = QAction("Update All HTML…", self, shortcut="Ctrl+Shift+U", triggered=self.handle_update_all_html)
        act_open_folder = QAction("Open Root Folder…", self, triggered=self._open_root_folder_dialog)
        act_exit = QAction("Exit", self, triggered=self.close)
        for a in (act_new_file, act_new_folder, act_rename, act_delete,
                  None, act_save, act_update_html, act_update_all,
                  None, act_open_folder, act_exit):
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

        # Help
        m_help = mb.addMenu("&Help")
        act_about = QAction("About", self, triggered=lambda: QMessageBox.information(self, "About", "miniPCB Studio — Website Manager"))
        m_help.addAction(act_about)

    # ---------------- AI Actions ----------------
    def _ai_generate_description(self):
        cur = self.editor.current_path()
        if not cur:
            QMessageBox.information(self, "AI", "Open a file first.")
            return
        seeds = ""  # hook up to a Seeds dialog/file if desired
        try:
            text = self.ai.generate_description(str(cur), seeds)
            existing = self.editor.edit.toPlainText()
            if str(cur).lower().endswith(".html"):
                new_text = existing + "\n\n<!-- AI Description -->\n" + text
            else:
                new_text = existing + "\n\n" + text
            self.editor.set_text(new_text)
            self.status.showMessage("AI description inserted", 3000)
        except Exception as e:
            QMessageBox.critical(self, "AI Error", str(e))

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
        cur = self.editor.current_path()
        if not cur:
            QMessageBox.information(self, "AI", "Open a file first.")
            return
        try:
            rows = self.ai.generate_testing(str(cur))
            headers = ["Test No.","Test Name","Test Description","Lower Limit","Target Value","Upper Limit","Units"]
            md = [
                "", "### Testing (AI)", "",
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join(["---"] * len(headers)) + " |"
            ]
            for r in rows:
                md.append("| " + " | ".join(str(x) for x in r) + " |")
            new_block = "\n".join(md) + "\n"
            self.editor.set_text(self.editor.edit.toPlainText() + "\n" + new_block)
            self.status.showMessage("AI Testing rows appended", 3000)
        except Exception as e:
            QMessageBox.critical(self, "AI Error", str(e))

    # ---------------- Actions ----------------
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
                import shutil; shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            self.status.showMessage("Deleted", 2000)
        except Exception as e:
            QMessageBox.critical(self, "Delete Error", str(e))

    def _open_root_folder_dialog(self):
        path = QFileDialog.getExistingDirectory(self, "Open Root Folder", str(self.ctx.project_root))
        if path:
            self._set_root(Path(path))

    def _open_pdf(self, path: Path):
        self.pdf.load_pdf(str(path))
        self.pdf.show()

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
        except Exception:
            pass

    # ---------------- Helpers ----------------
    def _current_root(self) -> Path:
        return self.ctx.project_root

    def _on_file_selected(self, path: str):
        self.editor.load_path(path)

    def _on_editor_path_loaded(self, p: Path):
        # Persist last opened file & folder
        try:
            self.ctx.settings.set("last_open_file", str(p))
            self.ctx.settings.set("last_open_folder", str(p.parent))
        except Exception:
            pass

    def _on_autosave_tick(self, remaining: int):
        if remaining > 0 and self.editor.is_dirty():
            self.autosave_label.setText(f"Autosave in {remaining}s")
        else:
            self.autosave_label.setText("Saved")
