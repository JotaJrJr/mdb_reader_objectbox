import pyodbc

try:
    import win32com.client as _win32
    _ADODB_AVAILABLE = True
except ImportError:
    _ADODB_AVAILABLE = False


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

_REGISTRY_HINTS = (
    "unable to open registry key",
    "temporary (volatile) ace dsn",
    "temporary (volatile)",
)

_CORRUPT_HINTS = (
    "not a database",
    "not recognize",
    "corrupt",
    "-1028",
    "unrecognized database format",
)


def _classify_error(err: Exception) -> MDBAccessError:
    raw = str(err)
    msg = raw.lower()
    sqlstate = ""
    if isinstance(err, pyodbc.Error) and err.args:
        sqlstate = err.args[0]

    if sqlstate == "IM014":
        return MDBAccessError("BITNESS_MISMATCH", raw, err)
    if sqlstate == "IM002":
        return MDBAccessError("DRIVER_MISSING", raw, err)
    if any(h in msg for h in _REGISTRY_HINTS):
        return MDBAccessError("REGISTRY_PERMISSION", raw, err)
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


def _try_odbc(path: str, extra: str = "") -> object:
    conn_str = f"Driver={{{_DRIVER}}};DBQ={path};{extra}"
    return pyodbc.connect(conn_str)


def _try_adodb(path: str, password: str = "") -> object:
    """ADODB connection via win32com — works with older Jet 3.x formats."""
    if not _ADODB_AVAILABLE:
        raise RuntimeError("pywin32 not available")
    conn = _win32.Dispatch("ADODB.Connection")
    pwd_part = f"Jet OLEDB:Database Password={password};" if password else ""
    # Try ACE first, fall back to Jet 4.0
    for provider in ("Microsoft.ACE.OLEDB.12.0", "Microsoft.Jet.OLEDB.4.0"):
        try:
            conn.ConnectionString = (
                f"Provider={provider};Data Source={path};"
                f"Persist Security Info=False;{pwd_part}"
            )
            conn.Open()
            return conn
        except Exception:
            pass
    raise RuntimeError("Neither ACE nor Jet OLEDB provider could open the file.")


class _AdobConnection:
    """Thin wrapper so ADODB behaves like a pyodbc connection for our purposes."""

    def __init__(self, adodb_conn, path: str):
        self._conn = adodb_conn
        self.path = path

    def cursor(self):
        return _AdobCursor(self._conn)

    def close(self):
        try:
            self._conn.Close()
        except Exception:
            pass

    # Schema introspection via ADODB OpenSchema
    def tables(self):
        from pywintypes import com_error
        rs = self._conn.OpenSchema(20)  # adSchemaTables
        names = []
        while not rs.EOF:
            ttype = rs.Fields("TABLE_TYPE").Value
            tname = rs.Fields("TABLE_NAME").Value
            if ttype == "TABLE" and not tname.startswith("MSys"):
                names.append(tname)
            rs.MoveNext()
        rs.Close()
        return names

    def columns(self, table: str):
        rs = self._conn.OpenSchema(4, [None, None, table])  # adSchemaColumns
        cols = []
        while not rs.EOF:
            cols.append({
                "name": rs.Fields("COLUMN_NAME").Value,
                "type": str(rs.Fields("DATA_TYPE").Value),
                "nullable": bool(rs.Fields("IS_NULLABLE").Value),
            })
            rs.MoveNext()
        rs.Close()
        return cols


class _AdobCursor:
    def __init__(self, conn):
        self._conn = conn
        self.description = None
        self._rows = []

    def execute(self, sql: str):
        try:
            rs, _ = self._conn.Execute(sql)
        except Exception as err:
            raise _classify_error(err) from err
        if rs is None or rs.State == 0:
            self._rows = []
            self.description = None
            return
        cols = [rs.Fields(i).Name for i in range(rs.Fields.Count)]
        self.description = [(c,) for c in cols]
        rows = []
        while not rs.EOF:
            rows.append(tuple(rs.Fields(i).Value for i in range(rs.Fields.Count)))
            rs.MoveNext()
        rs.Close()
        self._rows = rows

    def fetchall(self):
        return self._rows


class MDBConnection:
    def __init__(self, path: str):
        self.path = path
        self._conn = None
        self._backend: str = ""  # "odbc" | "adodb"

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def open(self, password: str = "") -> None:
        last_err = None

        # 1. Standard ODBC
        try:
            extra = f"PWD={password};" if password else ""
            self._conn = _try_odbc(self.path, extra)
            self._backend = "odbc"
            return
        except pyodbc.Error as e:
            classified = _classify_error(e)
            # Only fall through on file-format/corrupt errors; surface others immediately
            if classified.error_code not in ("FILE_CORRUPT", "UNKNOWN", "REGISTRY_PERMISSION"):
                raise classified from e
            last_err = classified

        # 2. ODBC with default Jet admin credentials
        try:
            extra = f"Uid=Admin;Pwd=;{'PWD=' + password + ';' if password else ''}"
            self._conn = _try_odbc(self.path, extra)
            self._backend = "odbc"
            return
        except pyodbc.Error:
            pass

        # 3. ADODB fallback (handles Jet 3.x and older formats)
        try:
            adodb_conn = _try_adodb(self.path, password)
            self._conn = _AdobConnection(adodb_conn, self.path)
            self._backend = "adodb"
            return
        except Exception as e:
            last_err = last_err or _classify_error(e)

        raise last_err or MDBAccessError("UNKNOWN", "All connection strategies failed.")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._backend = ""

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
