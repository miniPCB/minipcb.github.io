from PyQt5.QtWidgets import QAction
from PyQt5.QtGui import QKeySequence

def install_hotkeys(window):
    act_save = QAction("Save", window)
    act_save.setShortcut(QKeySequence.Save)
    act_save.triggered.connect(window.handle_save_current)
    window.addAction(act_save)

    act_update_all = QAction("Update All HTML", window)
    act_update_all.setShortcut("Ctrl+Shift+U")
    act_update_all.triggered.connect(window.handle_update_all_html)
    window.addAction(act_update_all)
