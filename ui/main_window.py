from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QLabel, QFileDialog, QFrame, QPushButton, QInputDialog, QLineEdit
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from core.connection import MDBConnection, MDBAccessError
from core.diagnostics import Diagnostic, diagnose
from core.schema import SchemaReader
from ui.sidebar import SidebarWidget
from ui.editor import EditorWidget
from ui.results import ResultsWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MDB Reader")
        self.resize(1200, 750)
        self._connection: MDBConnection | None = None
        self._setup_ui()
        # Accept drops on the window itself — no child widget needed
        self.setAcceptDrops(True)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ───────────────────────────────────────────────
        self.sidebar = SidebarWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.table_selected.connect(self._on_table_selected)
        root.addWidget(self.sidebar)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet("color: #e5e7eb;")
        root.addWidget(divider)

        # ── Right panel (stacked: welcome screen OR work area) ────
        self._right_stack = QWidget()
        self._right_layout = QVBoxLayout(self._right_stack)
        self._right_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._right_stack, 1)

        # Welcome / drop screen
        self._welcome = self._build_welcome()
        self._right_layout.addWidget(self._welcome)

        # Work area (editor + results) — hidden until file loaded
        self._work_area = QWidget()
        work_layout = QVBoxLayout(self._work_area)
        work_layout.setContentsMargins(8, 8, 8, 8)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.editor = EditorWidget()
        self.results = ResultsWidget()
        splitter.addWidget(self.editor)
        splitter.addWidget(self.results)
        splitter.setSizes([200, 400])
        work_layout.addWidget(splitter)
        self._work_area.setVisible(False)
        self._right_layout.addWidget(self._work_area)

        self.editor.execute_requested.connect(self._on_execute)
        self._setup_menu()

    def _build_welcome(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: #f9fafb;")
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        icon = QLabel("🗄")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 64px; background: transparent;")
        layout.addWidget(icon)

        label = QLabel("Drop a .mdb file here\nor click the button below")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 18px; color: #6b7280; background: transparent;")
        layout.addWidget(label)

        btn = QPushButton("Open .mdb file…")
        btn.setFixedWidth(200)
        btn.setFixedHeight(44)
        btn.setStyleSheet(
            "QPushButton { background: #2563eb; color: white; border-radius: 6px; font-size: 15px; }"
            "QPushButton:hover { background: #1d4ed8; }"
        )
        btn.clicked.connect(self._open_file_dialog)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("Supports .mdb (Microsoft Access)")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 12px; color: #9ca3af; background: transparent;")
        layout.addWidget(hint)

        return w

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

        # Show work area immediately — errors display there
        self._welcome.setVisible(False)
        self._work_area.setVisible(True)

        conn = MDBConnection(path)
        try:
            conn.open()
        except MDBAccessError as err:
            if err.error_code == "PASSWORD_REQUIRED":
                pwd, ok = QInputDialog.getText(
                    self, "Password Required",
                    "This file is password-protected.\nEnter the database password:",
                    QLineEdit.EchoMode.Password,
                )
                if ok and pwd:
                    try:
                        conn.open(password=pwd)
                    except MDBAccessError as err2:
                        self.results.show_error(diagnose(err2))
                        return
                else:
                    self.results.show_error(diagnose(err))
                    return
            else:
                self.results.show_error(diagnose(err))
                return
        except Exception as err:
            diag = Diagnostic(
                title=f"Unexpected Error: {type(err).__name__}",
                steps=[str(err), "Check that the file is a valid .mdb and is not corrupted."],
                severity="error",
            )
            self.results.show_error(diag)
            return

        self._connection = conn
        try:
            reader = SchemaReader(conn)
            tables = reader.get_all_tables()
        except Exception as err:
            diag = Diagnostic(
                title="Failed to Read Schema",
                steps=[str(err)],
                severity="error",
            )
            self.results.show_error(diag)
            return

        self.sidebar.load_tables(tables)
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
            self.results.show_error(diagnose(err))

    # ── Drag and drop on the main window ─────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".mdb"):
                self._load_file(path)
                event.acceptProposedAction()
                return
        event.ignore()

    def closeEvent(self, event):
        self._close_connection()
        super().closeEvent(event)
