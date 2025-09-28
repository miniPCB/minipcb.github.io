# studio/main.py
import sys, subprocess, importlib
from pathlib import Path

# ⬇️ Force the project root to your fixed Windows path
PROJECT_ROOT = Path(r"C:\Repos\minipcb.github.io").resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REQUIRED = {
    "PyQt5": "PyQt5==5.15.11",
    "PyQt5.QtWebEngineWidgets": "PyQtWebEngine==5.15.7",
    "bs4": "beautifulsoup4==4.12.3",
}

def ensure_deps():
    for mod, pip_name in REQUIRED.items():
        try:
            importlib.import_module(mod)
        except Exception:
            print(f"[miniPCB Studio] Installing missing dependency: {pip_name} ...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
            importlib.import_module(mod)

def main():
    ensure_deps()
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

    app = QApplication(sys.argv)
    app.setApplicationName("miniPCB Studio")

    from app.context import AppContext
    from ui.main_window import MainWindow

    ctx = AppContext(PROJECT_ROOT)
    win = MainWindow(ctx)
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
