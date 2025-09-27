from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant

class SimpleTableModel(QAbstractTableModel):
    def __init__(self, headers, rows=None, parent=None):
        super().__init__(parent)
        self.headers = list(headers)
        self.rows = list(rows) if rows else []

    def rowCount(self, parent=None):
        return len(self.rows)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        r, c = index.row(), index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            try:
                return self.rows[r][c]
            except Exception:
                return ""
        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return QVariant()
        if orientation == 1:  # Horizontal
            return self.headers[section]
        return section + 1

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False
        r, c = index.row(), index.column()
        while r >= len(self.rows):
            self.rows.append([""] * len(self.headers))
        self.rows[r][c] = value
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    def insertRowAt(self, row: int, data=None):
        self.beginInsertRows(self.createIndex(0,0).parent(), row, row)
        self.rows.insert(row, data or ["" for _ in self.headers])
        self.endInsertRows()

    def removeRowAt(self, row: int):
        if 0 <= row < len(self.rows):
            self.beginRemoveRows(self.createIndex(0,0).parent(), row, row)
            self.rows.pop(row)
            self.endRemoveRows()
