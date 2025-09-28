from pathlib import Path
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QMessageBox
from PyQt5.QtCore import pyqtSignal

class EditorPanel(QWidget):
    dirtyChanged = pyqtSignal(bool)
    pathLoaded = pyqtSignal(Path)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._current = None
        self._dirty = False

        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        self.edit = QPlainTextEdit(self)
        self.edit.textChanged.connect(self._on_text_changed)
        lay.addWidget(self.edit)

    def load_path(self, path: str):
        p = Path(path)
        if p.is_dir():
            return
        try:
            text = p.read_text(encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Open Error", str(e)); return
        self._current = p
        self.edit.blockSignals(True)
        self.edit.setPlainText(text)
        self.edit.blockSignals(False)
        self._set_dirty(False)
        self.pathLoaded.emit(p)

    def save_current(self) -> bool:
        if not self._current:
            return False
        try:
            self._current.write_text(self.edit.toPlainText(), encoding="utf-8")
            self._set_dirty(False)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))
            return False

    def is_dirty(self) -> bool:
        return self._dirty

    def current_path(self) -> Path:
        return self._current

    def set_text(self, text: str):
        self.edit.setPlainText(text)
        self._set_dirty(True)

    def _on_text_changed(self):
        self._set_dirty(True)

    def _set_dirty(self, val: bool):
        if self._dirty != val:
            self._dirty = val
            self.dirtyChanged.emit(val)
