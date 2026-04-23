import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt, QMimeData, QUrl
from PyQt6.QtWidgets import QApplication

from core.schema import TableMeta, ColumnMeta
from core.connection import MDBAccessError
from core.diagnostics import Diagnostic
from ui.main_window import MainWindow
from ui.sidebar import SidebarWidget
from ui.editor import EditorWidget
from ui.results import ResultsWidget


# ── Sidebar ──────────────────────────────────────────────────────────────────

class TestSidebarWidget:
    def test_populates_table_list(self, qtbot):
        sidebar = SidebarWidget()
        qtbot.addWidget(sidebar)
        tables = [
            TableMeta("Users", [ColumnMeta("id", "INTEGER", False)], row_count=10),
            TableMeta("Orders", [ColumnMeta("order_id", "INTEGER", False)], row_count=5),
        ]
        sidebar.load_tables(tables)
        assert sidebar.table_count() == 2

    def test_table_names_visible(self, qtbot):
        sidebar = SidebarWidget()
        qtbot.addWidget(sidebar)
        tables = [TableMeta("Products", [ColumnMeta("id", "INTEGER")], row_count=3)]
        sidebar.load_tables(tables)
        assert sidebar.table_name_at(0) == "Products"

    def test_click_emits_table_selected(self, qtbot):
        sidebar = SidebarWidget()
        qtbot.addWidget(sidebar)
        tables = [TableMeta("Users", [ColumnMeta("id", "INTEGER")], row_count=7)]
        sidebar.load_tables(tables)

        with qtbot.waitSignal(sidebar.table_selected, timeout=1000) as blocker:
            sidebar.simulate_click(0)
        assert blocker.args[0].name == "Users"

    def test_clear_removes_all(self, qtbot):
        sidebar = SidebarWidget()
        qtbot.addWidget(sidebar)
        tables = [TableMeta("T1", [], 0), TableMeta("T2", [], 0)]
        sidebar.load_tables(tables)
        sidebar.clear()
        assert sidebar.table_count() == 0

    def test_shows_row_count_in_detail(self, qtbot):
        sidebar = SidebarWidget()
        qtbot.addWidget(sidebar)
        tables = [TableMeta("Users", [ColumnMeta("id", "INTEGER")], row_count=42)]
        sidebar.load_tables(tables)
        detail = sidebar.detail_text_for(0)
        assert "42" in detail

    def test_shows_column_count_in_detail(self, qtbot):
        sidebar = SidebarWidget()
        qtbot.addWidget(sidebar)
        cols = [ColumnMeta("id", "INTEGER"), ColumnMeta("name", "VARCHAR")]
        tables = [TableMeta("Users", cols, row_count=1)]
        sidebar.load_tables(tables)
        detail = sidebar.detail_text_for(0)
        assert "2" in detail


# ── Editor ───────────────────────────────────────────────────────────────────

class TestEditorWidget:
    def test_initial_text_is_empty(self, qtbot):
        editor = EditorWidget()
        qtbot.addWidget(editor)
        assert editor.get_sql() == ""

    def test_set_and_get_sql(self, qtbot):
        editor = EditorWidget()
        qtbot.addWidget(editor)
        editor.set_sql("SELECT * FROM Users")
        assert editor.get_sql() == "SELECT * FROM Users"

    def test_execute_signal_fires_on_run(self, qtbot):
        editor = EditorWidget()
        qtbot.addWidget(editor)
        editor.set_sql("SELECT 1")

        with qtbot.waitSignal(editor.execute_requested, timeout=1000) as blocker:
            editor.trigger_execute()
        assert blocker.args[0] == "SELECT 1"

    def test_execute_signal_not_fired_when_empty(self, qtbot):
        editor = EditorWidget()
        qtbot.addWidget(editor)
        editor.set_sql("")

        signal_received = []
        editor.execute_requested.connect(lambda sql: signal_received.append(sql))
        editor.trigger_execute()
        assert signal_received == []

    def test_clear_resets_sql(self, qtbot):
        editor = EditorWidget()
        qtbot.addWidget(editor)
        editor.set_sql("SELECT * FROM Users")
        editor.clear()
        assert editor.get_sql() == ""


# ── Results ──────────────────────────────────────────────────────────────────

class TestResultsWidget:
    def test_show_results_populates_table(self, qtbot):
        results = ResultsWidget()
        qtbot.addWidget(results)
        columns = ["id", "name"]
        rows = [(1, "Alice"), (2, "Bob")]
        results.show_results(columns, rows)
        assert results.row_count() == 2
        assert results.column_count() == 2

    def test_column_headers_set_correctly(self, qtbot):
        results = ResultsWidget()
        qtbot.addWidget(results)
        results.show_results(["id", "email"], [(1, "a@b.com")])
        assert results.header_at(0) == "id"
        assert results.header_at(1) == "email"

    def test_clear_removes_data(self, qtbot):
        results = ResultsWidget()
        qtbot.addWidget(results)
        results.show_results(["id"], [(1,)])
        results.clear()
        assert results.row_count() == 0

    def test_show_error_displays_message(self, qtbot):
        results = ResultsWidget()
        qtbot.addWidget(results)
        diag = Diagnostic(title="Driver missing", steps=["Install driver"], severity="error")
        results.show_error(diag)
        assert results.error_visible()

    def test_row_count_label_updates(self, qtbot):
        results = ResultsWidget()
        qtbot.addWidget(results)
        results.show_results(["x"], [(i,) for i in range(15)])
        assert "15" in results.status_text()


# ── MainWindow ────────────────────────────────────────────────────────────────

class TestMainWindow:
    def test_window_creates_without_crash(self, qtbot):
        win = MainWindow()
        qtbot.addWidget(win)
        assert win is not None

    def test_starts_in_empty_state(self, qtbot):
        win = MainWindow()
        qtbot.addWidget(win)
        assert win.sidebar.table_count() == 0

    def test_load_file_populates_sidebar(self, qtbot):
        win = MainWindow()
        qtbot.addWidget(win)

        tables = [TableMeta("Users", [ColumnMeta("id", "INTEGER")], row_count=3)]
        schema_mock = MagicMock()
        schema_mock.list_tables.return_value = ["Users"]
        schema_mock.get_all_tables.return_value = tables

        with patch("ui.main_window.MDBConnection") as mock_conn_cls, \
             patch("ui.main_window.SchemaReader", return_value=schema_mock):
            mock_conn = MagicMock()
            mock_conn.is_open = True
            mock_conn_cls.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_conn_cls.return_value.is_open = True
            win._load_file("fake.mdb")

        assert win.sidebar.table_count() == 1

    def test_load_inaccessible_file_shows_error(self, qtbot):
        win = MainWindow()
        qtbot.addWidget(win)

        with patch("ui.main_window.MDBConnection") as mock_conn_cls:
            err = MDBAccessError("DRIVER_MISSING", "No driver")
            instance = MagicMock()
            instance.open.side_effect = err
            mock_conn_cls.return_value = instance
            win._load_file("fake.mdb")

        assert win.results.error_visible()
