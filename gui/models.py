from PySide6.QtCore import QAbstractListModel, QModelIndex, QSortFilterProxyModel, Qt


class Rows(QAbstractListModel):
    """A typed-role list model, updated exclusively on the application thread."""
    def __init__(self, roles, parent=None):
        super().__init__(parent)
        self.rows = []
        self._roles = {Qt.UserRole + i + 1: name.encode() for i, name in enumerate(roles)}

    def roleNames(self):
        return self._roles

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        name = self._roles.get(role)
        return self.rows[index.row()].get(name.decode()) if name else None

    def replace(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def refresh(self, rows):
        """Like replace(), but rows that are still the same rows (same count) are changed in place,
        so a view keeps its scroll position and focus instead of starting over at the top."""
        if len(rows) != len(self.rows):
            self.replace(rows)
            return
        for i, row in enumerate(rows):
            changed = {k: v for k, v in row.items() if self.rows[i].get(k) != v}
            if changed:
                self.change(i, **changed)

    def change(self, row, **values):
        if 0 <= row < len(self.rows):
            self.rows[row].update(values)
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [r for r, n in self._roles.items() if n.decode() in values])


class SelectedChapters(QSortFilterProxyModel):
    def __init__(self, chapters, parent=None):
        super().__init__(parent)
        self.setSourceModel(chapters)
        self.setFilterRole(next(role for role, name in chapters.roleNames().items() if name == b'included'))

    def filterAcceptsRow(self, row, parent):
        source = self.sourceModel()
        return bool(source.data(source.index(row, 0, parent), self.filterRole()))
