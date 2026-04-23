import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import pyodbc

from core.connection import MDBConnection, MDBAccessError


class TestMDBConnectionInit:
    def test_stores_path(self, sample_mdb_path):
        conn = MDBConnection(sample_mdb_path)
        assert conn.path == sample_mdb_path

    def test_not_connected_on_init(self, sample_mdb_path):
        conn = MDBConnection(sample_mdb_path)
        assert not conn.is_open


class TestMDBConnectionOpen:
    def test_open_succeeds(self, sample_mdb_path, mock_pyodbc_connect):
        mock_connect, mock_conn, _ = mock_pyodbc_connect
        conn = MDBConnection(sample_mdb_path)
        conn.open()
        assert conn.is_open
        mock_connect.assert_called_once()

    def test_connection_string_contains_path(self, sample_mdb_path, mock_pyodbc_connect):
        mock_connect, _, _ = mock_pyodbc_connect
        conn = MDBConnection(sample_mdb_path)
        conn.open()
        call_args = mock_connect.call_args[0][0]
        assert sample_mdb_path in call_args

    def test_driver_missing_raises_access_error(self, sample_mdb_path):
        err = pyodbc.Error("IM002", "[IM002] Data source name not found")
        with patch("pyodbc.connect", side_effect=err):
            conn = MDBConnection(sample_mdb_path)
            with pytest.raises(MDBAccessError) as exc_info:
                conn.open()
        assert exc_info.value.error_code == "DRIVER_MISSING"

    def test_password_protected_raises_access_error(self, sample_mdb_path):
        err = pyodbc.Error("28000", "[28000] Not a valid password")
        with patch("pyodbc.connect", side_effect=err):
            conn = MDBConnection(sample_mdb_path)
            with pytest.raises(MDBAccessError) as exc_info:
                conn.open()
        assert exc_info.value.error_code == "PASSWORD_REQUIRED"

    def test_file_locked_raises_access_error(self, sample_mdb_path):
        err = pyodbc.Error("HY000", "[HY000] (3045)")
        with patch("pyodbc.connect", side_effect=err):
            conn = MDBConnection(sample_mdb_path)
            with pytest.raises(MDBAccessError) as exc_info:
                conn.open()
        assert exc_info.value.error_code == "FILE_LOCKED"

    def test_workgroup_security_raises_access_error(self, sample_mdb_path):
        err = pyodbc.Error("28000", "[28000] (3029) You do not have necessary permissions")
        with patch("pyodbc.connect", side_effect=err):
            conn = MDBConnection(sample_mdb_path)
            with pytest.raises(MDBAccessError) as exc_info:
                conn.open()
        assert exc_info.value.error_code == "WORKGROUP_SECURITY"

    def test_bitness_mismatch_raises_access_error(self, sample_mdb_path):
        err = pyodbc.Error("IM014", "[IM014] The specified DSN contains an architecture mismatch")
        with patch("pyodbc.connect", side_effect=err):
            conn = MDBConnection(sample_mdb_path)
            with pytest.raises(MDBAccessError) as exc_info:
                conn.open()
        assert exc_info.value.error_code == "BITNESS_MISMATCH"


class TestMDBConnectionClose:
    def test_close_sets_not_open(self, sample_mdb_path, mock_pyodbc_connect):
        _, mock_conn, _ = mock_pyodbc_connect
        conn = MDBConnection(sample_mdb_path)
        conn.open()
        conn.close()
        assert not conn.is_open
        mock_conn.close.assert_called_once()

    def test_close_when_not_open_is_safe(self, sample_mdb_path):
        conn = MDBConnection(sample_mdb_path)
        conn.close()  # must not raise


class TestMDBConnectionExecute:
    def test_execute_returns_rows(self, sample_mdb_path, mock_pyodbc_connect):
        _, mock_conn, mock_cursor = mock_pyodbc_connect
        mock_cursor.fetchall.return_value = [(1, "Alice"), (2, "Bob")]
        mock_cursor.description = [("id",), ("name",)]

        conn = MDBConnection(sample_mdb_path)
        conn.open()
        rows, columns = conn.execute("SELECT id, name FROM Users")

        assert rows == [(1, "Alice"), (2, "Bob")]
        assert columns == ["id", "name"]

    def test_execute_raises_if_not_open(self, sample_mdb_path):
        conn = MDBConnection(sample_mdb_path)
        with pytest.raises(RuntimeError):
            conn.execute("SELECT 1")

    def test_execute_sql_error_raises_access_error(self, sample_mdb_path, mock_pyodbc_connect):
        _, mock_conn, mock_cursor = mock_pyodbc_connect
        mock_cursor.execute.side_effect = pyodbc.Error("42000", "[42000] Syntax error")

        conn = MDBConnection(sample_mdb_path)
        conn.open()
        with pytest.raises(MDBAccessError) as exc_info:
            conn.execute("SELECT bad syntax !!!")
        assert exc_info.value.error_code == "QUERY_ERROR"


class TestMDBConnectionContextManager:
    def test_context_manager_opens_and_closes(self, sample_mdb_path, mock_pyodbc_connect):
        _, mock_conn, _ = mock_pyodbc_connect
        with MDBConnection(sample_mdb_path) as conn:
            assert conn.is_open
        assert not conn.is_open
        mock_conn.close.assert_called_once()

    def test_context_manager_closes_on_exception(self, sample_mdb_path, mock_pyodbc_connect):
        _, mock_conn, _ = mock_pyodbc_connect
        with pytest.raises(ValueError):
            with MDBConnection(sample_mdb_path) as conn:
                raise ValueError("boom")
        mock_conn.close.assert_called_once()
def test_fail(): assert False
