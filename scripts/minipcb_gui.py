import sys
import os
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QPushButton, QTextEdit, QLabel, QSplitter, QMessageBox, QTextBrowser
)
from PyQt6.QtCore import Qt


class MiniPCBApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("miniPCB HTML Manager")
        self.setMinimumSize(1000, 700)

        self.base_dirs = ["./00A", "./04A", "./04B", "./05", "./06", "./08H", "./09A", "./09H", "./10", "."]

        self.init_ui()

    def init_ui(self):
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.file_list.itemSelectionChanged.connect(self.load_selected_file)

        self.viewer = QTextBrowser()

        right_panel = QVBoxLayout()

        self.load_files_btn = QPushButton("Load HTML Files")
        self.load_files_btn.clicked.connect(self.populate_file_list)

        self.script_list = QListWidget()
        self.populate_script_list()
        self.script_list.setMaximumHeight(100)

        self.run_script_btn = QPushButton("Run Script on Selected")
        self.run_script_btn.clicked.connect(self.run_script_on_selected)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)

        right_panel.addWidget(self.load_files_btn)
        right_panel.addWidget(QLabel("Available Scripts:"))
        right_panel.addWidget(self.script_list)
        right_panel.addWidget(self.run_script_btn)
        right_panel.addWidget(QLabel("Log Output:"))
        right_panel.addWidget(self.log_output)

        right_widget = QWidget()
        right_widget.setLayout(right_panel)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.file_list)
        splitter.addWidget(self.viewer)
        splitter.setStretchFactor(1, 1)

        main_widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(splitter)
        layout.addWidget(right_widget)
        main_widget.setLayout(layout)

        self.setCentralWidget(main_widget)
        self.populate_file_list()

    def populate_file_list(self):
        self.file_list.clear()
        found = 0
        for folder in self.base_dirs:
            for root, _, files in os.walk(folder):
                for file in files:
                    if file.endswith(".html"):
                        full_path = os.path.join(root, file)
                        self.file_list.addItem(full_path)
                        found += 1
        self.log_output.append(f"Loaded {found} HTML files.")

    def populate_script_list(self):
        self.script_list.clear()
        current_file = os.path.basename(__file__)
        script_dir = os.path.dirname(__file__)
        for file in os.listdir(script_dir):
            if file.endswith(".py") and file != current_file:
                self.script_list.addItem(file)

    def load_selected_file(self):
        selected = self.file_list.selectedItems()
        if not selected:
            return
        file_path = selected[0].text()
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                html = f.read()
            self.viewer.setHtml(html)
        except Exception as e:
            self.log_output.append(f"Error loading file: {file_path}\n{e}")

    def run_script_on_selected(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select at least one HTML file.")
            return

        script_item = self.script_list.currentItem()
        if not script_item:
            QMessageBox.warning(self, "No Script Selected", "Please select a script to run.")
            return

        script_name = script_item.text()
        script_path = os.path.join(os.path.dirname(__file__), script_name)

        html_files = [item.text() for item in selected_items]

        try:
            result = subprocess.run(
                [sys.executable, script_path] + html_files,
                capture_output=True,
                text=True
            )
            self.log_output.append(f"▶ Running {script_name}...\n")
            if result.stdout:
                self.log_output.append(result.stdout)
            if result.stderr:
                self.log_output.append("⚠ STDERR:\n" + result.stderr)
        except Exception as e:
            self.log_output.append(f"✖ Error running script:\n{e}")

        self.log_output.append("✅ Script completed.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MiniPCBApp()
    window.show()
    sys.exit(app.exec())
