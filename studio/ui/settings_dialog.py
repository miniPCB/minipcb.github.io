from pathlib import Path
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QHBoxLayout,
    QFileDialog, QSpinBox, QDialogButtonBox
)

class SettingsDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Settings")
        lay = QFormLayout(self)

        # Root folder
        self.root_edit = QLineEdit(str(self.ctx.project_root))
        btn_root = QPushButton("Browse…")
        btn_root.clicked.connect(self._pick_root)
        hb_root = QHBoxLayout(); hb_root.addWidget(self.root_edit); hb_root.addWidget(btn_root)
        lay.addRow("Root folder:", hb_root)

        # Templates dir
        self.templates_edit = QLineEdit(str(self.ctx.templates_dir))
        btn_t = QPushButton("Browse…"); btn_t.clicked.connect(self._pick_templates)
        hb_t = QHBoxLayout(); hb_t.addWidget(self.templates_edit); hb_t.addWidget(btn_t)
        lay.addRow("Templates dir:", hb_t)

        # Images dir
        self.images_edit = QLineEdit(str(self.ctx.images_dir))
        btn_i = QPushButton("Browse…"); btn_i.clicked.connect(self._pick_images)
        hb_i = QHBoxLayout(); hb_i.addWidget(self.images_edit); hb_i.addWidget(btn_i)
        lay.addRow("Images dir:", hb_i)

        # Autosave seconds
        self.autosave_sb = QSpinBox()
        self.autosave_sb.setRange(5, 3600)
        self.autosave_sb.setValue(int(self.ctx.settings.get("autosave_seconds", 30)))
        lay.addRow("Autosave (seconds):", self.autosave_sb)

        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addRow(self.buttons)

    def _pick_root(self):
        path = QFileDialog.getExistingDirectory(self, "Choose root folder", self.root_edit.text())
        if path: self.root_edit.setText(path)

    def _pick_templates(self):
        path = QFileDialog.getExistingDirectory(self, "Choose templates dir", self.templates_edit.text())
        if path: self.templates_edit.setText(path)

    def _pick_images(self):
        path = QFileDialog.getExistingDirectory(self, "Choose images dir", self.images_edit.text())
        if path: self.images_edit.setText(path)

    def values(self) -> dict:
        return {
            "project_root": Path(self.root_edit.text()),
            "templates_dir": Path(self.templates_edit.text()),
            "images_dir": Path(self.images_edit.text()),
            "autosave_seconds": int(self.autosave_sb.value())
        }
