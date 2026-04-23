from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel

from core.schema import TableMeta


class SidebarWidget(QWidget):
    table_selected = pyqtSignal(object)  # emits TableMeta

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tables: list[TableMeta] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("Tables")
        layout.addWidget(self._label)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree)

    def load_tables(self, tables: list[TableMeta]):
        self._tables = tables
        self._tree.clear()
        for table in tables:
            item = QTreeWidgetItem([table.name])
            item.setData(0, 256, table)  # Qt.UserRole = 256
            self._tree.addTopLevelItem(item)

    def clear(self):
        self._tables = []
        self._tree.clear()

    def table_count(self) -> int:
        return self._tree.topLevelItemCount()

    def table_name_at(self, index: int) -> str:
        return self._tree.topLevelItem(index).text(0)

    def detail_text_for(self, index: int) -> str:
        table: TableMeta = self._tree.topLevelItem(index).data(0, 256)
        return f"Rows: {table.row_count} | Columns: {len(table.columns)}"

    def simulate_click(self, index: int):
        item = self._tree.topLevelItem(index)
        self._tree.itemClicked.emit(item, 0)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        table: TableMeta = item.data(0, 256)
        if table:
            self.table_selected.emit(table)
