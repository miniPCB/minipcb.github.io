from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
try:
    # Prefer absolute import (works when studio root is on sys.path)
    from services.pdf_service import PdfViewFactory
except Exception:
    # Fallback if executed as a package where relative works
    from ..services.pdf_service import PdfViewFactory

class PdfPanel(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF Viewer")
        self.resize(900, 700)
        lay = QVBoxLayout(self)
        self.view = PdfViewFactory.create()
        if self.view is None:
            lay.addWidget(QLabel("QtWebEngine not available. Cannot render PDF inline."))
            return
        lay.addWidget(self.view)
        btns = QHBoxLayout()
        self.btn_in = QPushButton("+"); self.btn_out = QPushButton("-"); self.btn_reset = QPushButton("100%")
        btns.addWidget(self.btn_out); btns.addWidget(self.btn_reset); btns.addWidget(self.btn_in)
        lay.addLayout(btns)
        self.zoom = 1.0
        self.btn_in.clicked.connect(self._zoom_in)
        self.btn_out.clicked.connect(self._zoom_out)
        self.btn_reset.clicked.connect(self._zoom_reset)

    def load_pdf(self, file_path: str):
        if self.view:
            PdfViewFactory.load_pdf(self.view, file_path)

    def _apply_zoom(self):
        if self.view:
            PdfViewFactory.set_zoom(self.view, self.zoom)

    def _zoom_in(self):
        self.zoom = min(3.0, self.zoom + 0.1); self._apply_zoom()

    def _zoom_out(self):
        self.zoom = max(0.2, self.zoom - 0.1); self._apply_zoom()

    def _zoom_reset(self):
        self.zoom = 1.0; self._apply_zoom()
