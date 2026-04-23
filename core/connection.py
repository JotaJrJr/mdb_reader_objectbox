import pyodbc


class MDBAccessError(Exception):
    def __init__(self, error_code: str, message: str, original: Exception = None):
        super().__init__(message)
        self.error_code = error_code
        self.original = original


_DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"


_PASSWORD_HINTS = (
    "not a valid password",
    "invalid password",
    "password",
    "-1507",
)

_WORKGROUP_HINTS = (
    "(3029)",
    "(3033)",
    "do not have the necessary permissions",
    "workgroup",
)

_LOCK_HINTS = (
    "(3045)",
    "already in use",
    "file already in use",
    "exclusive",
)

_CORRUPT_HINTS = (
    "not a database",
    "not recognize",
    "corrupt",
    "-1028",
    "unrecognized database format",
)


def _classify_error(err: pyodbc.Error) -> MDBAccessError:
    msg = str(err).lower()
    raw = str(err)
    sqlstate = err.args[0] if err.args else ""

    if sqlstate == "IM014":
        return MDBAccessError("BITNESS_MISMATCH", raw, err)
    if sqlstate == "IM002":
        return MDBAccessError("DRIVER_MISSING", raw, err)
    if any(h in msg for h in _LOCK_HINTS):
        return MDBAccessError("FILE_LOCKED", raw, err)
    if any(h in msg for h in _WORKGROUP_HINTS):
        return MDBAccessError("WORKGROUP_SECURITY", raw, err)
    if sqlstate == "28000" or any(h in msg for h in _PASSWORD_HINTS):
        return MDBAccessError("PASSWORD_REQUIRED", raw, err)
    if any(h in msg for h in _CORRUPT_HINTS):
        return MDBAccessError("FILE_CORRUPT", raw, err)
    if sqlstate in ("42000", "37000") or "syntax error" in msg:
        return MDBAccessError("QUERY_ERROR", raw, err)
    return MDBAccessError("UNKNOWN", raw, err)


class MDBConnection:
    def __init__(self, path: str):
        self.path = path
        self._conn = None

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def open(self, password: str = "") -> None:
        if password:
            conn_str = f"Driver={{{_DRIVER}}};DBQ={self.path};PWD={password};"
        else:
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
