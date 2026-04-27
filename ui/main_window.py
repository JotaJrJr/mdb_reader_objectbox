import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QLabel, QFileDialog, QFrame, QPushButton, QInputDialog, QLineEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from core.connection import MDBConnection, MDBAccessError
from core.custom_reader import (
    CustomConnection, CustomSchemaReader, is_custom_format, load_ob_schema,
)
from core.diagnostics import Diagnostic, diagnose
from core.schema import SchemaReader
from ui.sidebar import SidebarWidget
from ui.editor import EditorWidget
from ui.results import ResultsWidget
from ui.history import HistoryWidget


class _QueryWorker(QThread):
    finished = pyqtSignal(list, list)   # rows, columns
    error = pyqtSignal(str)

    def __init__(self, conn, sql: str):
        super().__init__()
        self._conn = conn
        self._sql = sql

    def run(self):
        try:
            rows, columns = self._conn.execute(self._sql)
            self.finished.emit(rows, columns)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MDB Reader")
        self.resize(1200, 750)
        self._connection: MDBConnection | None = None
        self._custom_connection: CustomConnection | None = None
        self._ob_schema: dict | None = None
        self._worker: _QueryWorker | None = None
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

        # Work area (editor + results + history) — hidden until file loaded
        self._work_area = QWidget()
        work_layout = QVBoxLayout(self._work_area)
        work_layout.setContentsMargins(0, 0, 0, 0) # Remove margins, using splitter padding
        
        # Main horizontal splitter for work area
        self._work_h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._work_h_splitter.setHandleWidth(1)
        self._work_h_splitter.setStyleSheet("QSplitter::handle { background: #e5e7eb; }")

        # Left side: Vertical splitter for Editor and Results
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(8, 8, 8, 8)
        
        self._v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.editor = EditorWidget()
        self.results = ResultsWidget()
        self._v_splitter.addWidget(self.editor)
        self._v_splitter.addWidget(self.results)
        self._v_splitter.setSizes([200, 400])
        left_layout.addWidget(self._v_splitter)
        
        # Right side: History
        self.history = HistoryWidget()
        self.history.setFixedWidth(240)
        self.history.query_selected.connect(self.editor.set_sql)

        self._work_h_splitter.addWidget(left_pane)
        self._work_h_splitter.addWidget(self.history)
        
        work_layout.addWidget(self._work_h_splitter)
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
        self._schema_action = file_menu.addAction("Load ObjectBox schema…")
        self._schema_action.triggered.connect(self._load_schema_dialog)
        self._schema_action.setEnabled(False)
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

        # ── Try standard Jet/ACE ODBC/ADODB path ─────────────────
        conn = MDBConnection(path)
        standard_failed = False
        _odbc_err = None
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
            elif err.error_code in ("FILE_CORRUPT", "UNKNOWN", "REGISTRY_PERMISSION"):
                # FILE_CORRUPT / UNKNOWN  → file is not a standard MDB.
                # REGISTRY_PERMISSION     → ODBC is broken; the file might still be
                #   a custom (ObjectBox) format.  Try that path before giving up.
                standard_failed = True
                _odbc_err = err
            else:
                self.results.show_error(diagnose(err))
                return
        except Exception:
            standard_failed = True

        if standard_failed:
            if is_custom_format(path):
                schema = self._find_schema_near(path)
                self._load_custom(path, schema=schema)
            elif _odbc_err and _odbc_err.error_code == "REGISTRY_PERMISSION":
                # Real Access file but ODBC registry is broken — show that specific error.
                self.results.show_error(diagnose(_odbc_err))
            else:
                diag = Diagnostic(
                    title="File May Be Corrupted or Unrecognised",
                    steps=[
                        "The file could not be opened by any Access driver.",
                        "Verify the file is a valid .mdb database.",
                        "If the file came from another application it may use a proprietary format.",
                    ],
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

    def _find_schema_near(self, path: str) -> dict | None:
        """Look for objectbox-model.json in the same directory as path."""
        candidate = os.path.join(os.path.dirname(os.path.abspath(path)), "objectbox-model.json")
        if os.path.isfile(candidate):
            return load_ob_schema(candidate)
        return None

    def _load_custom(self, path: str, schema: dict | None = None):
        custom = CustomConnection(path, schema=schema)
        try:
            custom.open()
        except Exception as err:
            diag = Diagnostic(
                title="Failed to Read Custom Format",
                steps=[str(err)],
                severity="error",
            )
            self.results.show_error(diag)
            return

        self._custom_connection = custom
        self._ob_schema = schema
        self._schema_action.setEnabled(True)
        reader = CustomSchemaReader(custom)
        tables = reader.get_all_tables()
        self.sidebar.load_tables(tables)
        schema_note = " [+schema]" if schema else ""
        self.setWindowTitle(f"MDB Reader — {path} [custom format{schema_note}]")

        if not schema:
            diag = Diagnostic(
                title="ObjectBox Schema Missing",
                steps=[
                    "The file was opened in custom mode, but no schema (objectbox-model.json) was found.",
                    "Table names and some fields may be guessed or incomplete.",
                    "Go to 'File > Load ObjectBox schema...' to provide the schema file from your Flutter project.",
                ],
                severity="warning",
            )
            self.results.show_error(diag)

    def _load_schema_dialog(self):
        """Let user point to an objectbox-model.json to re-parse the current file."""
        if not (self._custom_connection and self._custom_connection.is_open):
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load ObjectBox Schema", "",
            "ObjectBox Schema (objectbox-model.json);;All Files (*)",
        )
        if not path:
            return
        schema = load_ob_schema(path)
        if schema is None:
            diag = Diagnostic(
                title="Invalid Schema File",
                steps=["Could not parse the selected file as objectbox-model.json."],
                severity="error",
            )
            self.results.show_error(diag)
            return
        self.results.show_loading()
        self._load_custom(self._custom_connection.path, schema=schema)

    def _close_connection(self):
        if self._connection and self._connection.is_open:
            self._connection.close()
        self._connection = None
        if self._custom_connection and self._custom_connection.is_open:
            self._custom_connection.close()
        self._custom_connection = None

    def _on_table_selected(self, table):
        sql = f"SELECT * FROM [{table.name}]"
        self.editor.set_sql(sql)

    def _on_execute(self, sql: str):
        conn = self._custom_connection if (self._custom_connection and self._custom_connection.is_open) \
               else self._connection if (self._connection and self._connection.is_open) \
               else None
        if conn is None:
            return

        # Cancel previous worker if still running
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(500)

        self.results.show_loading()
        self.editor.setEnabled(False)
        
        # Add to history
        self.history.add_entry(sql, "pending")

        self._worker = _QueryWorker(conn, sql)
        self._worker.finished.connect(self._on_query_done)
        self._worker.error.connect(self._on_query_error)
        self._worker.finished.connect(lambda *_: self.editor.setEnabled(True))
        self._worker.error.connect(lambda *_: self.editor.setEnabled(True))
        self._worker.start()

    def _on_query_done(self, rows: list, columns: list):
        self.results.show_results(columns, rows)
        self.history.update_last_entry("success")

    def _on_query_error(self, msg: str):
        diag = Diagnostic(title="Query Error", steps=[msg], severity="error")
        self.results.show_error(diag)
        self.history.update_last_entry("error")

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
