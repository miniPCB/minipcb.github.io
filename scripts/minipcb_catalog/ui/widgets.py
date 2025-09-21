from __future__ import annotations
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QFileIconProvider, QApplication, QStyle, QSizePolicy
from PyQt5.QtGui import QPixmap

class PlainIconProvider(QFileIconProvider):
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

class FitImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._orig: QPixmap | None = None
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
