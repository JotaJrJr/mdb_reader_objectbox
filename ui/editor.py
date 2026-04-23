from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton


class EditorWidget(QWidget):
    execute_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("Enter SQL query here… (F5 or Ctrl+Enter to execute)")
        layout.addWidget(self._editor)

        btn_row = QHBoxLayout()
        self._run_btn = QPushButton("Run (F5)")
        self._run_btn.clicked.connect(self.trigger_execute)
        btn_row.addStretch()
        btn_row.addWidget(self._run_btn)
        layout.addLayout(btn_row)

        f5 = QShortcut(QKeySequence("F5"), self)
        f5.activated.connect(self.trigger_execute)

        ctrl_enter = QShortcut(QKeySequence("Ctrl+Return"), self)
        ctrl_enter.activated.connect(self.trigger_execute)

    def get_sql(self) -> str:
        return self._editor.toPlainText()

    def set_sql(self, sql: str):
        self._editor.setPlainText(sql)

    def clear(self):
        self._editor.clear()

    def trigger_execute(self):
        sql = self.get_sql().strip()
        if sql:
            self.execute_requested.emit(sql)
