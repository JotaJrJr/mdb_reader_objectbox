from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QLabel, QFileDialog, QFrame
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from core.connection import MDBConnection, MDBAccessError
from core.schema import SchemaReader
from core.diagnostics import diagnose
from ui.sidebar import SidebarWidget
from ui.editor import EditorWidget
from ui.results import ResultsWidget


class _DropArea(QLabel):
    """Centered drop-target shown before any file is loaded."""

    def __init__(self, on_file_dropped, parent=None):
        super().__init__(parent)
        self._callback = on_file_dropped
        self.setText("Open or drop a .mdb file here")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "border: 2px dashed #9ca3af; border-radius: 8px; "
            "color: #6b7280; font-size: 18px; background: #f9fafb;"
        )
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".mdb"):
                self._callback(path)
                return


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MDB Reader")
        self.resize(1200, 750)
        self._connection: MDBConnection | None = None
        self._setup_ui()
        self.setAcceptDrops(True)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        self.sidebar = SidebarWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.table_selected.connect(self._on_table_selected)

        # Right panel: drop area | editor + results
        self._right_stack = QWidget()
        right_layout = QVBoxLayout(self._right_stack)
        right_layout.setContentsMargins(8, 8, 8, 8)

        self._drop_area = _DropArea(self._load_file)
        right_layout.addWidget(self._drop_area)

        self._work_area = QWidget()
        work_layout = QVBoxLayout(self._work_area)
        work_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.editor = EditorWidget()
        self.results = ResultsWidget()
        splitter.addWidget(self.editor)
        splitter.addWidget(self.results)
        splitter.setSizes([200, 400])
        work_layout.addWidget(splitter)

        self._work_area.setVisible(False)
        right_layout.addWidget(self._work_area)

        root.addWidget(self.sidebar)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet("color: #e5e7eb;")
        root.addWidget(divider)

        root.addWidget(self._right_stack, 1)

        self.editor.execute_requested.connect(self._on_execute)

        self._setup_menu()

    def _setup_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        open_action = file_menu.addAction("Open .mdb file…")
        open_action.triggered.connect(self._open_file_dialog)
        file_menu.addSeparator()
        file_menu.addAction("Exit").triggered.connect(self.close)

    def _open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open MDB File", "", "Access Databases (*.mdb);;All Files (*)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        self._close_connection()
        self.sidebar.clear()
        self.results.clear()

        conn = MDBConnection(path)
        try:
            conn.open()
        except MDBAccessError as err:
            diag = diagnose(err)
            self.results.show_error(diag)
            self._drop_area.setVisible(True)
            self._work_area.setVisible(False)
            return

        self._connection = conn
        reader = SchemaReader(conn)
        tables = reader.get_all_tables()
        self.sidebar.load_tables(tables)

        self._drop_area.setVisible(False)
        self._work_area.setVisible(True)
        self.setWindowTitle(f"MDB Reader — {path}")

    def _close_connection(self):
        if self._connection and self._connection.is_open:
            self._connection.close()
        self._connection = None

    def _on_table_selected(self, table):
        sql = f"SELECT * FROM [{table.name}]"
        self.editor.set_sql(sql)

    def _on_execute(self, sql: str):
        if not self._connection or not self._connection.is_open:
            return
        try:
            rows, columns = self._connection.execute(sql)
            self.results.show_results(columns, rows)
        except MDBAccessError as err:
            diag = diagnose(err)
            self.results.show_error(diag)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".mdb"):
                self._load_file(path)
                return

    def closeEvent(self, event):
        self._close_connection()
        super().closeEvent(event)
