import pytest
from unittest.mock import MagicMock, patch

from core.schema import TableMeta, ColumnMeta, SchemaReader


def _make_connection(tables=None, columns=None, row_count=0):
    """Build a mock MDBConnection with configurable schema responses."""
    conn = MagicMock()
    conn.is_open = True

    def execute_side_effect(sql):
        sql_upper = sql.strip().upper()
        if "SELECT COUNT(*)" in sql_upper:
            return [(row_count,)], ["count"]
        return [], []

    conn.execute.side_effect = execute_side_effect

    # pyodbc cursor for schema introspection
    mock_cursor = MagicMock()
    mock_inner = MagicMock()
    conn._conn = mock_inner

    if tables is not None:
        mock_cursor.tables.return_value = [
            MagicMock(table_name=t, table_type="TABLE") for t in tables
        ]
    else:
        mock_cursor.tables.return_value = []

    if columns is not None:
        def columns_side_effect(table=None):
            return [
                MagicMock(column_name=c["name"], type_name=c["type"], nullable=c.get("nullable", True))
                for c in (columns.get(table) or [])
            ]
        mock_cursor.columns.side_effect = columns_side_effect
    else:
        mock_cursor.columns.return_value = []

    mock_inner.cursor.return_value = mock_cursor
    return conn


class TestColumnMeta:
    def test_stores_fields(self):
        col = ColumnMeta(name="id", type_name="INTEGER", nullable=False)
        assert col.name == "id"
        assert col.type_name == "INTEGER"
        assert col.nullable is False


class TestTableMeta:
    def test_stores_name_and_columns(self):
        cols = [ColumnMeta("id", "INTEGER", False), ColumnMeta("name", "VARCHAR", True)]
        table = TableMeta(name="Users", columns=cols, row_count=42)
        assert table.name == "Users"
        assert len(table.columns) == 2
        assert table.row_count == 42

    def test_column_names_property(self):
        cols = [ColumnMeta("id", "INTEGER", False), ColumnMeta("email", "VARCHAR", True)]
        table = TableMeta(name="Accounts", columns=cols, row_count=0)
        assert table.column_names == ["id", "email"]


class TestSchemaReader:
    def test_list_tables_returns_names(self):
        conn = _make_connection(tables=["Users", "Orders"])
        reader = SchemaReader(conn)
        names = reader.list_tables()
        assert names == ["Users", "Orders"]

    def test_list_tables_excludes_system_tables(self):
        conn = _make_connection(tables=["Users", "MSysObjects"])
        mock_cursor = conn._conn.cursor.return_value
        mock_cursor.tables.return_value = [
            MagicMock(table_name="Users", table_type="TABLE"),
            MagicMock(table_name="MSysObjects", table_type="SYSTEM TABLE"),
        ]
        reader = SchemaReader(conn)
        names = reader.list_tables()
        assert "MSysObjects" not in names
        assert "Users" in names

    def test_get_table_meta_returns_table_meta(self):
        col_data = {"Users": [{"name": "id", "type": "INTEGER", "nullable": False},
                               {"name": "username", "type": "VARCHAR", "nullable": True}]}
        conn = _make_connection(tables=["Users"], columns=col_data, row_count=10)
        reader = SchemaReader(conn)
        meta = reader.get_table_meta("Users")

        assert isinstance(meta, TableMeta)
        assert meta.name == "Users"
        assert meta.row_count == 10
        assert len(meta.columns) == 2
        assert meta.columns[0].name == "id"
        assert meta.columns[0].type_name == "INTEGER"

    def test_get_table_meta_row_count_uses_execute(self):
        col_data = {"Products": [{"name": "id", "type": "INTEGER"}]}
        conn = _make_connection(tables=["Products"], columns=col_data, row_count=99)
        reader = SchemaReader(conn)
        meta = reader.get_table_meta("Products")
        assert meta.row_count == 99

    def test_get_all_tables_returns_list_of_meta(self):
        col_data = {
            "Users": [{"name": "id", "type": "INTEGER"}],
            "Orders": [{"name": "order_id", "type": "INTEGER"}],
        }
        conn = _make_connection(tables=["Users", "Orders"], columns=col_data, row_count=5)
        reader = SchemaReader(conn)
        all_meta = reader.get_all_tables()
        assert len(all_meta) == 2
        assert {t.name for t in all_meta} == {"Users", "Orders"}

    def test_schema_reader_requires_open_connection(self):
        conn = MagicMock()
        conn.is_open = False
        reader = SchemaReader(conn)
        with pytest.raises(RuntimeError):
            reader.list_tables()
