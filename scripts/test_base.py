import json
import os
import sys
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QSplitter,
    QTabWidget, QFileDialog, QPlainTextEdit, QFormLayout, QLineEdit, QLabel,
    QPushButton, QListWidget, QMessageBox, QComboBox, QSpinBox, QDoubleSpinBox,
    QToolBar, QAction, QFrame, QStyleFactory, QLineEdit
)

APP_NAME = "TestBASE JSON Manager"
ORG_NAME = "TestBASE"


# -------------------- Theming --------------------
def apply_dark_palette(app: QApplication) -> None:
    """Apply a nice dark theme without external dependencies."""
    app.setStyle(QStyleFactory.create("Fusion"))
    dark = QPalette()

    # Core colors
    bg = QColor(30, 30, 30)
    base = QColor(36, 36, 36)
    alt_base = QColor(44, 44, 44)
    text = QColor(220, 220, 220)
    disabled_text = QColor(140, 140, 140)
    btn = QColor(53, 53, 53)
    hl = QColor(42, 130, 218)

    dark.setColor(QPalette.Window, bg)
    dark.setColor(QPalette.WindowText, text)
    dark.setColor(QPalette.Base, base)
    dark.setColor(QPalette.AlternateBase, alt_base)
    dark.setColor(QPalette.ToolTipBase, text)
    dark.setColor(QPalette.ToolTipText, text)
    dark.setColor(QPalette.Text, text)
    dark.setColor(QPalette.Disabled, QPalette.Text, disabled_text)
    dark.setColor(QPalette.Button, btn)
    dark.setColor(QPalette.ButtonText, text)
    dark.setColor(QPalette.Disabled, QPalette.ButtonText, disabled_text)
    dark.setColor(QPalette.Highlight, hl)
    dark.setColor(QPalette.HighlightedText, QColor(255, 255, 255))

    app.setPalette(dark)

    app.setStyleSheet("""
        QToolTip { color: #eee; background-color: #333; border: 1px solid #444; }
        QListWidget::item:selected { background: #2a82da; color: white; }
        QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            border: 1px solid #444; border-radius: 6px; padding: 4px;
            background-color: #242424; color: #e6e6e6;
        }
        QPushButton {
            border: 1px solid #444; border-radius: 6px; padding: 6px 10px;
            background-color: #2e2e2e;
        }
        QPushButton:hover { background-color: #383838; }
        QPushButton:pressed { background-color: #1f1f1f; }
        QTabBar::tab {
            background: #2b2b2b; padding: 8px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px;
        }
        QTabBar::tab:selected { background: #353535; }
        QStatusBar { background: #1e1e1e; }
        QFrame#BrandBadge { background: #111; border: 1px solid #333; border-radius: 10px; }
    """)


def is_multiline_string(value: str) -> bool:
    return isinstance(value, str) and ("\n" in value or len(value) > 120)


# -------------------- Main Window --------------------
class JSONEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setGeometry(80, 80, 1200, 800)

        self.settings = QSettings(ORG_NAME, APP_NAME)

        self.json_folder: str = ""
        self.current_edit_file: str = ""
        self.json_widgets = {}

        self._build_ui()
        self._connect_actions()

        # Restore last folder
        last_dir = self.settings.value("last_dir", type=str)
        if last_dir and os.path.isdir(last_dir):
            self.load_json_files(last_dir)

    # ---------- UI ----------
    def _build_ui(self):
        # Toolbar
        self.toolbar = QToolBar("Main")
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        self.act_open = QAction("Open Folder…", self)
        self.act_open.setShortcut("Ctrl+O")
        self.toolbar.addAction(self.act_open)

        self.act_refresh = QAction("Refresh", self)
        self.act_refresh.setShortcut("F5")
        self.toolbar.addAction(self.act_refresh)

        self.toolbar.addSeparator()

        self.act_save = QAction("Save", self)
        self.act_save.setShortcut("Ctrl+S")
        self.toolbar.addAction(self.act_save)

        self.act_validate = QAction("Validate JSON", self)
        self.act_validate.setShortcut("Ctrl+Shift+V")
        self.toolbar.addAction(self.act_validate)

        self.toolbar.addSeparator()
        self.act_about = QAction("About TestBASE", self)
        self.toolbar.addAction(self.act_about)

        # Central splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left panel (search + list + brand)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search .json files…")
        left_layout.addWidget(self.search_box)

        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        left_layout.addWidget(self.file_list, 1)

        brand = QFrame()
        brand.setObjectName("BrandBadge")
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(10, 10, 10, 10)
        brand_title = QLabel("TestBASE")
        brand_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        brand_sub = QLabel("JSON Manager")
        brand_sub.setStyleSheet("color: #aaa;")
        brand_layout.addWidget(brand_title)
        brand_layout.addWidget(brand_sub)
        left_layout.addWidget(brand)

        splitter.addWidget(left_panel)

        # Right panel (tabs)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(8)

        self.tabs = QTabWidget()
        self.form_tab = QWidget()
        self.raw_tab = QWidget()
        self.tabs.addTab(self.form_tab, "Form")
        self.tabs.addTab(self.raw_tab, "Raw")
        right_layout.addWidget(self.tabs, 1)
        splitter.addWidget(right_panel)

        # Build tabs
        self._setup_form_tab()
        self._setup_raw_tab()

        self.setCentralWidget(splitter)

        # Status bar
        self.statusBar().showMessage("Ready")

    def _setup_form_tab(self):
        outer = QVBoxLayout()
        self.edit_form = QFormLayout()
        self.edit_form.setSpacing(8)
        self.json_widgets = {}

        container = QWidget()
        container.setLayout(self.edit_form)

        outer.addWidget(QLabel("Top-level fields"))
        outer.addWidget(container, 1)

        btn_row = QHBoxLayout()
        self.btn_save_form = QPushButton("Save Changes")
        self.btn_reload_form = QPushButton("Reload")
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_reload_form)
        btn_row.addWidget(self.btn_save_form)
        outer.addLayout(btn_row)

        self.form_tab.setLayout(outer)

    def _setup_raw_tab(self):
        layout = QVBoxLayout()
        self.raw_editor = QPlainTextEdit()
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setFamily("Consolas, 'Courier New', monospace")
        mono.setPointSize(10)
        self.raw_editor.setFont(mono)

        layout.addWidget(QLabel("Raw JSON (editable)"))
        layout.addWidget(self.raw_editor, 1)

        btn_row = QHBoxLayout()
        self.btn_validate_raw = QPushButton("Validate JSON")
        self.btn_save_raw = QPushButton("Save")
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_validate_raw)
        btn_row.addWidget(self.btn_save_raw)

        layout.addLayout(btn_row)
        self.raw_tab.setLayout(layout)

    # ---------- Actions ----------
    def _connect_actions(self):
        self.act_open.triggered.connect(self._choose_folder)
        self.act_refresh.triggered.connect(self._refresh_file_list)
        self.act_save.triggered.connect(self._save_current_tab)
        self.act_validate.triggered.connect(self._validate_current_tab)
        self.act_about.triggered.connect(self._about)

        self.file_list.itemClicked.connect(self._on_file_clicked)
        self.search_box.textChanged.connect(self._apply_search_filter)

        self.btn_save_form.clicked.connect(self.save_edited_file_from_form)
        self.btn_reload_form.clicked.connect(self._reload_form_from_disk)

        self.btn_validate_raw.clicked.connect(self._validate_raw_editor)
        self.btn_save_raw.clicked.connect(self.save_edited_file_from_raw)

    # ---------- Behavior ----------
    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.load_json_files(folder)

    def load_json_files(self, folder: str):
        self.json_folder = folder
        self.settings.setValue("last_dir", folder)
        self.statusBar().showMessage(f"Loaded folder: {folder}")
        self._refresh_file_list()

    def _refresh_file_list(self):
        if not getattr(self, "json_folder", "") or not os.path.isdir(self.json_folder):
            return
        needle = self.search_box.text().strip().lower()
        self.file_list.clear()
        try:
            files = sorted([f for f in os.listdir(self.json_folder) if f.lower().endswith(".json")])
            for name in files:
                if not needle or needle in name.lower():
                    self.file_list.addItem(name)
            self.statusBar().showMessage(f"{self.file_list.count()} JSON file(s) found")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to list files: {e}")

    def _apply_search_filter(self, _):
        self._refresh_file_list()

    def _on_file_clicked(self, item):
        filename = item.text()
        self._load_file(filename)

    def _load_file(self, filename: str):
        try:
            file_path = os.path.join(self.json_folder, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)
            self.current_edit_file = filename

            # Raw tab content
            self.raw_editor.setPlainText(json.dumps(content, indent=2, ensure_ascii=False))

            # Form tab
            self._populate_form(content)

            # Land on Form tab first
            self.tabs.setCurrentWidget(self.form_tab)
            self.statusBar().showMessage(f"Loaded: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file: {e}")

    def _reload_form_from_disk(self):
        if not self.current_edit_file:
            return
        self._load_file(self.current_edit_file)

    # ---------- Form helpers ----------
    def _clear_form(self):
        while self.edit_form.count():
            item = self.edit_form.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.json_widgets.clear()

    def _populate_form(self, content: dict):
        self._clear_form()
        if not isinstance(content, dict):
            # Only top-level dict supported in Form tab
            self.edit_form.addRow(QLabel("Top-level JSON is not an object; edit in Raw tab."))
            return

        for key, value in content.items():
            label = QLabel(key)

            if value is None:
                widget = QComboBox()
                widget.addItems(["null", "true", "false"])
                widget.setCurrentIndex(0)
            elif isinstance(value, bool):
                widget = QComboBox()
                widget.addItems(["true", "false"])
                widget.setCurrentText("true" if value else "false")
            elif isinstance(value, int):
                widget = QSpinBox()
                widget.setMinimum(-2_147_483_648)
                widget.setMaximum(2_147_483_647)
                widget.setValue(value)
            elif isinstance(value, float):
                widget = QDoubleSpinBox()
                widget.setDecimals(6)
                widget.setMinimum(-1e12)
                widget.setMaximum(1e12)
                widget.setValue(value)
            elif isinstance(value, str) and is_multiline_string(value):
                widget = QPlainTextEdit(value)
                widget.setMinimumHeight(90)
            else:
                widget = QLineEdit("" if value is None else str(value))

            self.edit_form.addRow(label, widget)
            self.json_widgets[key] = widget

    def _gather_form_data(self) -> dict:
        data = {}
        for key, widget in self.json_widgets.items():
            if isinstance(widget, QSpinBox):
                data[key] = int(widget.value())
            elif isinstance(widget, QDoubleSpinBox):
                data[key] = float(widget.value())
            elif isinstance(widget, QComboBox):
                text = widget.currentText()
                if text == "null":
                    data[key] = None
                elif text == "true":
                    data[key] = True
                elif text == "false":
                    data[key] = False
                else:
                    data[key] = text
            elif isinstance(widget, QPlainTextEdit):
                data[key] = widget.toPlainText()
            elif isinstance(widget, QLineEdit):
                data[key] = widget.text()
            else:
                try:
                    data[key] = widget.text()
                except Exception:
                    data[key] = None
        return data

    # ---------- Save / Validate ----------
    def _current_file_path(self) -> str:
        if not self.json_folder or not self.current_edit_file:
            raise RuntimeError("No file selected.")
        return os.path.join(self.json_folder, self.current_edit_file)

    def save_edited_file_from_form(self):
        try:
            updated = self._gather_form_data()
            # validate round-trip
            json.dumps(updated)
            path = self._current_file_path()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(updated, f, indent=4, ensure_ascii=False)
            self.statusBar().showMessage(f"Saved: {self.current_edit_file}")
            # also refresh raw editor
            self.raw_editor.setPlainText(json.dumps(updated, indent=2, ensure_ascii=False))
            QMessageBox.information(self, "Success", "File saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def _validate_raw_editor(self):
        try:
            json.loads(self.raw_editor.toPlainText())
            QMessageBox.information(self, "Valid", "JSON is valid.")
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Invalid JSON", f"{e}")

    def save_edited_file_from_raw(self):
        try:
            parsed = json.loads(self.raw_editor.toPlainText())
            path = self._current_file_path()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, indent=4, ensure_ascii=False)
            self.statusBar().showMessage(f"Saved: {self.current_edit_file}")
            # also refresh form
            self._populate_form(parsed)
            QMessageBox.information(self, "Success", "File saved successfully.")
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Error", f"Invalid JSON: {e}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def _save_current_tab(self):
        current = self.tabs.currentWidget()
        if current is self.form_tab:
            self.save_edited_file_from_form()
        elif current is self.raw_tab:
            self.save_edited_file_from_raw()

    def _validate_current_tab(self):
        current = self.tabs.currentWidget()
        if current is self.raw_tab:
            self._validate_raw_editor()
        elif current is self.form_tab:
            try:
                json.dumps(self._gather_form_data())
                QMessageBox.information(self, "Valid", "Form data would serialize as valid JSON.")
            except TypeError as e:
                QMessageBox.critical(self, "Invalid", f"Form contains non-serializable data: {e}")

    def _about(self):
        QMessageBox.information(
            self,
            "About TestBASE",
            "TestBASE JSON Manager\n\n"
            "A fast, dark-mode editor for browsing and editing JSON files.\n"
            "• Left: Search & select JSON files\n"
            "• Right: Form editor and Raw JSON editor\n\n"
            "Shortcuts:\n"
            "  Ctrl+O  Open Folder\n"
            "  Ctrl+S  Save\n"
            "  F5      Refresh\n"
            "  Ctrl+Shift+V  Validate JSON\n\n"
            "© TestBASE"
        )


# -------------------- Entry --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_dark_palette(app)
    editor = JSONEditor()
    editor.show()
    sys.exit(app.exec_())
