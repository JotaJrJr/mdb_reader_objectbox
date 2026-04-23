from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QFrame, QHBoxLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.diagnostics import Diagnostic


class ResultsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._error_visible = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Error banner
        self._error_frame = QFrame()
        self._error_frame.setStyleSheet(
            "background:#fef2f2; border:1px solid #fca5a5; border-radius:4px; padding:4px;"
        )
        error_layout = QVBoxLayout(self._error_frame)
        self._error_title = QLabel()
        self._error_title.setStyleSheet("font-weight:bold; color:#b91c1c;")
        self._error_steps = QLabel()
        self._error_steps.setWordWrap(True)
        self._error_steps.setStyleSheet("color:#7f1d1d;")
        error_layout.addWidget(self._error_title)
        error_layout.addWidget(self._error_steps)
        self._error_frame.setVisible(False)
        layout.addWidget(self._error_frame)

        # Results table
        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

        # Status bar
        self._status = QLabel("")
        self._status.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self._status)

    def show_results(self, columns: list[str], rows: list[tuple]):
        self._error_frame.setVisible(False)
        self._error_visible = False
        self._table.clear()
        self._table.setColumnCount(len(columns))
        self._table.setRowCount(len(rows))
        self._table.setHorizontalHeaderLabels(columns)

        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                self._table.setItem(r, c, QTableWidgetItem(str(val) if val is not None else ""))

        self._table.resizeColumnsToContents()
        self._status.setText(f"{len(rows)} row(s) returned")

    def show_error(self, diag: Diagnostic):
        self._error_title.setText(diag.title)
        self._error_steps.setText("\n".join(f"• {s}" for s in diag.steps))
        self._error_frame.setVisible(True)
        self._error_visible = True
        self._table.clear()
        self._table.setRowCount(0)
        self._status.setText("")

    def clear(self):
        self._table.clear()
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._error_frame.setVisible(False)
        self._error_visible = False
        self._status.setText("")

    def error_visible(self) -> bool:
        return self._error_visible

    def row_count(self) -> int:
        return self._table.rowCount()

    def column_count(self) -> int:
        return self._table.columnCount()

    def header_at(self, col: int) -> str:
        item = self._table.horizontalHeaderItem(col)
        return item.text() if item else ""

    def status_text(self) -> str:
        return self._status.text()
