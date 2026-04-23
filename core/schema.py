from dataclasses import dataclass, field
from typing import List

from core.connection import MDBConnection


@dataclass
class ColumnMeta:
    name: str
    type_name: str
    nullable: bool = True


@dataclass
class TableMeta:
    name: str
    columns: List[ColumnMeta]
    row_count: int = 0

    @property
    def column_names(self) -> List[str]:
        return [c.name for c in self.columns]


class SchemaReader:
    def __init__(self, connection: MDBConnection):
        self._conn = connection

    def _require_open(self):
        if not self._conn.is_open:
            raise RuntimeError("Connection must be open before reading schema.")

    def list_tables(self) -> List[str]:
        self._require_open()
        cursor = self._conn._conn.cursor()
        return [
            row.table_name
            for row in cursor.tables()
            if row.table_type == "TABLE"
        ]

    def get_table_meta(self, table_name: str) -> TableMeta:
        self._require_open()
        cursor = self._conn._conn.cursor()
        columns = [
            ColumnMeta(
                name=col.column_name,
                type_name=col.type_name,
                nullable=bool(col.nullable),
            )
            for col in cursor.columns(table=table_name)
        ]
        rows, _ = self._conn.execute(f"SELECT COUNT(*) FROM [{table_name}]")
        row_count = rows[0][0] if rows else 0
        return TableMeta(name=table_name, columns=columns, row_count=row_count)

    def get_all_tables(self) -> List[TableMeta]:
        return [self.get_table_meta(name) for name in self.list_tables()]
