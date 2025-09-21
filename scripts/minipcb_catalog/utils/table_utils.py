from __future__ import annotations
from typing import List
from PyQt5.QtWidgets import QTableWidget, QHeaderView

def make_table(headers: List[str]) -> QTableWidget:
    tbl = QTableWidget(0, len(headers))
    tbl.setHorizontalHeaderLabels(headers)
    tbl.verticalHeader().setVisible(False)
    for i in range(len(headers)):
        mode = QHeaderView.Stretch if i == len(headers)-1 else QHeaderView.ResizeToContents
        tbl.horizontalHeader().setSectionResizeMode(i, mode)
    return tbl
