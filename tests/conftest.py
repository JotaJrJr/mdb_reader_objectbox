import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_pyodbc_connect(monkeypatch):
    """Patch pyodbc.connect to avoid real ODBC calls."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []
    mock_cursor.description = None

    with patch("pyodbc.connect", return_value=mock_conn) as mock_connect:
        yield mock_connect, mock_conn, mock_cursor


@pytest.fixture
def sample_mdb_path(tmp_path):
    """Fake .mdb file path (file does not need to exist for unit tests)."""
    f = tmp_path / "test.mdb"
    f.write_bytes(b"")  # empty placeholder
    return str(f)
