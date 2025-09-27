import os, shutil
from pathlib import Path
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTreeView, QFileSystemModel, QMenu, QInputDialog, QMessageBox
from PyQt5.QtCore import pyqtSignal, Qt, QPoint
from services.file_service import FileService

class FolderTree(QWidget):
    fileSelected = pyqtSignal(str)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.fs = FileService(self.ctx.project_root)
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)

        self.model = QFileSystemModel(self)
        self.model.setReadOnly(False)

        self.view = QTreeView(self)
        self.view.setModel(self.model)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        # Single-click selection:
        self.view.clicked.connect(self._on_clicked)

        # Drag & Drop move support
        self.view.setDragEnabled(True)
        self.view.setAcceptDrops(True)
        self.view.setDropIndicatorShown(True)
        self.view.setDragDropMode(QTreeView.DragDrop)
        self.view.setDefaultDropAction(Qt.MoveAction)

        lay.addWidget(self.view)
        self.set_root(self.ctx.project_root)

    def set_root(self, root_path: Path):
        self.model.setRootPath(str(root_path))
        self.view.setRootIndex(self.model.index(str(root_path)))

    # ------- Events -------
    def _on_clicked(self, idx):
        path = self.model.filePath(idx)
        if path:
            self.fileSelected.emit(path)

    def _on_context_menu(self, pos: QPoint):
        idx = self.view.indexAt(pos)
        global_pos = self.view.viewport().mapToGlobal(pos)
        menu = QMenu(self)

        act_new_file = menu.addAction("New File…")
        act_new_folder = menu.addAction("New Folder…")
        menu.addSeparator()
        act_rename = menu.addAction("Rename…")
        act_delete = menu.addAction("Delete…")

        selected_action = menu.exec_(global_pos)
        # Resolve target directory and path
        if idx.isValid():
            target_path = Path(self.model.filePath(idx))
        else:
            target_path = Path(self.ctx.project_root)

        if selected_action == act_new_file:
            self._new_file(target_path)
        elif selected_action == act_new_folder:
            self._new_folder(target_path)
        elif selected_action == act_rename:
            self._rename(target_path)
        elif selected_action == act_delete:
            self._delete(target_path)

    # ------- Operations -------
    def _new_file(self, target_path: Path):
        folder = target_path if target_path.is_dir() else target_path.parent
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if not ok or not name.strip(): return
        p = folder / name.strip()
        if p.exists():
            QMessageBox.warning(self, "Exists", "File already exists."); return
        p.write_text("", encoding="utf-8")

    def _new_folder(self, target_path: Path):
        folder = target_path if target_path.is_dir() else target_path.parent
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok or not name.strip(): return
        p = folder / name.strip()
        if p.exists():
            QMessageBox.warning(self, "Exists", "Folder already exists."); return
        p.mkdir(parents=True, exist_ok=False)

    def _rename(self, target_path: Path):
        base = target_path
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=base.name)
        if not ok or not new_name.strip(): return
        dst = base.with_name(new_name.strip())
        try:
            os.replace(base, dst)
        except Exception as e:
            QMessageBox.critical(self, "Rename Error", str(e))

    def _delete(self, target_path: Path):
        if QMessageBox.question(self, "Delete", f"Delete '{target_path.name}'?") != QMessageBox.Yes:
            return
        try:
            if target_path.is_dir():
                shutil.rmtree(target_path)
            else:
                target_path.unlink(missing_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Delete Error", str(e))
