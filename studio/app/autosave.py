from PyQt5.QtCore import QObject, QTimer, pyqtSignal

class AutoSaver(QObject):
    tick = pyqtSignal(int)  # seconds remaining
    trigger_save = pyqtSignal()

    def __init__(self, interval_seconds: int = 30, parent=None):
        super().__init__(parent)
        self.interval = max(5, int(interval_seconds))
        self.remaining = self.interval
        self._dirty = False
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    def set_dirty(self, is_dirty: bool):
        self._dirty = is_dirty
        if is_dirty:
            self.remaining = self.interval

    def start(self):
        self._timer.start()

    def reset(self):
        self.remaining = self.interval

    def _on_tick(self):
        if not self._dirty:
            self.tick.emit(self.remaining)
            return
        self.remaining -= 1
        if self.remaining <= 0:
            self.trigger_save.emit()
            self.remaining = self.interval
        self.tick.emit(self.remaining)
