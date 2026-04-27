import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QFrame, QHBoxLayout, QPushButton, QSizePolicy,
    QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.diagnostics import Diagnostic

PAGE_SIZE = 500


class ResultsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._error_visible = False
        self._all_rows: list[tuple] = []
        self._columns: list[str] = []
        self._page = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Error banner
        self._error_frame = QFrame()
        self._error_frame.setStyleSheet(
            "background:#fef2f2; border:1px solid #fca5a5; border-radius:4px; padding:4px; margin:4px;"
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

        # Loading indicator
        self._loading = QLabel("  Loading…")
        self._loading.setStyleSheet("color:#6b7280; font-size:13px; padding:8px;")
        self._loading.setVisible(False)
        layout.addWidget(self._loading)

        # Results table
        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        layout.addWidget(self._table)

        # Bottom bar: status + pagination
        bar = QWidget()
        bar.setStyleSheet("background:#f9fafb; border-top:1px solid #e5e7eb;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#6b7280; font-size:12px;")
        bar_layout.addWidget(self._status)

        bar_layout.addStretch()

        self._btn_prev = QPushButton("◀ Prev")
        self._btn_prev.setFixedHeight(26)
        self._btn_prev.setStyleSheet(
            "QPushButton{background:#e5e7eb;border-radius:4px;font-size:12px;padding:0 8px;}"
            "QPushButton:hover{background:#d1d5db;}"
            "QPushButton:disabled{color:#9ca3af;}"
        )
        self._btn_prev.clicked.connect(self._prev_page)

        self._page_label = QLabel("")
        self._page_label.setStyleSheet("color:#374151; font-size:12px; padding:0 6px;")

        self._btn_next = QPushButton("Next ▶")
        self._btn_next.setFixedHeight(26)
        self._btn_next.setStyleSheet(
            "QPushButton{background:#e5e7eb;border-radius:4px;font-size:12px;padding:0 8px;}"
            "QPushButton:hover{background:#d1d5db;}"
            "QPushButton:disabled{color:#9ca3af;}"
        )
        self._btn_next.clicked.connect(self._next_page)

        bar_layout.addWidget(self._btn_prev)
        bar_layout.addWidget(self._page_label)
        bar_layout.addWidget(self._btn_next)

        bar.setFixedHeight(36)
        layout.addWidget(bar)

        self._set_pagination_visible(False)

    # ── Public API ────────────────────────────────────────────────

    def show_loading(self):
        self._loading.setVisible(True)
        self._table.setVisible(False)
        self._error_frame.setVisible(False)
        self._status.setText("")
        self._set_pagination_visible(False)

    def show_results(self, columns: list[str], rows: list[tuple]):
        self._loading.setVisible(False)
        self._table.setVisible(True)
        self._error_frame.setVisible(False)
        self._error_visible = False
        self._all_rows = rows
        self._columns = columns
        self._page = 0
        self._render_page()

    def show_error(self, diag: Diagnostic):
        self._loading.setVisible(False)
        self._error_title.setText(diag.title)
        self._error_steps.setText("\n".join(f"• {s}" for s in diag.steps))
        self._error_frame.setVisible(True)
        self._error_visible = True
        self._table.clear()
        self._table.setRowCount(0)
        self._status.setText("")
        self._set_pagination_visible(False)

    def clear(self):
        self._loading.setVisible(False)
        self._table.clear()
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._error_frame.setVisible(False)
        self._error_visible = False
        self._status.setText("")
        self._all_rows = []
        self._columns = []
        self._page = 0
        self._set_pagination_visible(False)

    # ── Pagination ────────────────────────────────────────────────

    def _total_pages(self) -> int:
        if not self._all_rows:
            return 1
        return max(1, (len(self._all_rows) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _render_page(self):
        start = self._page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_rows = self._all_rows[start:end]

        self._table.setSortingEnabled(False)
        self._table.clear()
        
        # We add an extra column at the beginning for the "JSON" copy button
        display_cols = ["JSON"] + self._columns
        self._table.setColumnCount(len(display_cols))
        self._table.setRowCount(len(page_rows))
        self._table.setHorizontalHeaderLabels(display_cols)

        for r, row in enumerate(page_rows):
            # 1. Add the Copy JSON button
            btn = QPushButton("{}")
            btn.setToolTip("Copy row as JSON")
            btn.setFixedSize(24, 20)
            btn.setStyleSheet(
                "QPushButton { background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe; border-radius: 4px; font-weight: bold; font-size: 10px; }"
                "QPushButton:hover { background: #dbeafe; }"
                "QPushButton:pressed { background: #bfdbfe; }"
            )
            # Use a closure to capture the correct absolute index
            abs_idx = start + r
            btn.clicked.connect(lambda _, idx=abs_idx: self._copy_row_as_json(idx))
            
            # Center the button in the cell
            container = QWidget()
            btn_layout = QHBoxLayout(container)
            btn_layout.setContentsMargins(2, 0, 2, 0)
            btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_layout.addWidget(btn)
            self._table.setCellWidget(r, 0, container)

            # 2. Add the data columns
            for c, val in enumerate(row):
                self._table.setItem(r, c + 1, QTableWidgetItem(str(val) if val is not None else ""))

        self._table.resizeColumnsToContents()
        self._table.setSortingEnabled(True)

        total = len(self._all_rows)
        pages = self._total_pages()
        self._status.setText(
            f"{total:,} row(s) — showing {start + 1}–{min(end, total):,}"
        )

        if pages > 1:
            self._set_pagination_visible(True)
            self._page_label.setText(f"Page {self._page + 1} / {pages}")
            self._btn_prev.setEnabled(self._page > 0)
            self._btn_next.setEnabled(self._page < pages - 1)
        else:
            self._set_pagination_visible(False)

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._render_page()

    def _next_page(self):
        if self._page < self._total_pages() - 1:
            self._page += 1
            self._render_page()

    def _set_pagination_visible(self, visible: bool):
        self._btn_prev.setVisible(visible)
        self._btn_next.setVisible(visible)
        self._page_label.setVisible(visible)

    def _copy_row_as_json(self, abs_idx: int):
        if abs_idx < 0 or abs_idx >= len(self._all_rows):
            return
        
        row_tuple = self._all_rows[abs_idx]
        obj = {}
        for col_name, val in zip(self._columns, row_tuple):
            # Try to parse strings as JSON if they look like it (to avoid double escaping)
            if isinstance(val, str) and val.strip().startswith(("{", "[")):
                try:
                    obj[col_name] = json.loads(val)
                    continue
                except:
                    pass
            obj[col_name] = val
            
        json_str = json.dumps(obj, indent=2, ensure_ascii=False)
        QApplication.clipboard().setText(json_str)
        
        # Optional: update status bar to show success
        orig_status = self._status.text()
        self._status.setText("✓ Row copied to clipboard as JSON!")
        self._status.setStyleSheet("color: #059669; font-weight: bold; font-size: 12px;")
        
        # Reset status after 2 seconds
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self._reset_status(orig_status))

    def _reset_status(self, text: str):
        self._status.setText(text)
        self._status.setStyleSheet("color:#6b7280; font-size:12px;")

    # ── Test helpers ──────────────────────────────────────────────

    def error_visible(self) -> bool:
        return self._error_visible

    def row_count(self) -> int:
        return self._table.rowCount()

    def column_count(self) -> int:
        return max(0, self._table.columnCount() - 1)  # exclude JSON copy column

    def header_at(self, col: int) -> str:
        item = self._table.horizontalHeaderItem(col + 1)  # offset past JSON copy column
        return item.text() if item else ""

    def status_text(self) -> str:
        return self._status.text()
