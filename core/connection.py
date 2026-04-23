import pyodbc


class MDBAccessError(Exception):
    def __init__(self, error_code: str, message: str, original: Exception = None):
        super().__init__(message)
        self.error_code = error_code
        self.original = original


_DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"


def _classify_error(err: pyodbc.Error) -> MDBAccessError:
    msg = str(err)
    sqlstate = err.args[0] if err.args else ""

    if sqlstate == "IM014":
        return MDBAccessError("BITNESS_MISMATCH", "32/64-bit driver mismatch. Match Python bitness to installed ACE driver.", err)
    if sqlstate == "IM002":
        return MDBAccessError("DRIVER_MISSING", "Microsoft Access ODBC driver not found. Install Access Database Engine 2016.", err)
    if "(3045)" in msg:
        return MDBAccessError("FILE_LOCKED", "File is locked exclusively by another process. Close Microsoft Access.", err)
    if "(3029)" in msg:
        return MDBAccessError("WORKGROUP_SECURITY", "Workgroup security (.mdw) required. Contact the database administrator.", err)
    if sqlstate == "28000":
        return MDBAccessError("PASSWORD_REQUIRED", "File is password-protected. Re-open with correct password.", err)
    if sqlstate in ("42000", "37000"):
        return MDBAccessError("QUERY_ERROR", f"SQL error: {msg}", err)
    return MDBAccessError("UNKNOWN", f"Unexpected error ({sqlstate}): {msg}", err)


class MDBConnection:
    def __init__(self, path: str):
        self.path = path
        self._conn = None

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def open(self) -> None:
        conn_str = f"Driver={{{_DRIVER}}};DBQ={self.path};"
        try:
            self._conn = pyodbc.connect(conn_str)
        except pyodbc.Error as err:
            raise _classify_error(err) from err

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def execute(self, sql: str) -> tuple[list, list[str]]:
        if not self.is_open:
            raise RuntimeError("Connection is not open. Call open() first.")
        cursor = self._conn.cursor()
        try:
            cursor.execute(sql)
        except pyodbc.Error as err:
            raise _classify_error(err) from err
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return rows, columns

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
