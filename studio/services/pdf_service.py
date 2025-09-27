try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    from PyQt5.QtCore import QUrl
except Exception:
    QWebEngineView = None
    QUrl = None

class PdfViewFactory:
    @staticmethod
    def create():
        if QWebEngineView is None:
            return None
        view = QWebEngineView()
        return view

    @staticmethod
    def load_pdf(view, file_path: str):
        if view is None:
            return
        view.load(QUrl.fromLocalFile(file_path))

    @staticmethod
    def set_zoom(view, factor: float):
        if view is None:
            return
        view.setZoomFactor(factor)
