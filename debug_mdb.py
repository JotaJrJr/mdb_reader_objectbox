"""Run: python debug_mdb.py "C:\path\to\your\file.mdb" """
import sys
import pyodbc
import win32com.client as w

path = sys.argv[1] if len(sys.argv) > 1 else input("Paste .mdb path: ").strip().strip('"')

print(f"\nTesting: {path}\n{'='*60}")

# ── Strategy 1: ODBC standard ────────────────────────────────
print("\n[1] ODBC standard")
try:
    c = pyodbc.connect(f"Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={path};")
    print("    SUCCESS")
    c.close()
except Exception as e:
    print(f"    FAIL: {e}")

# ── Strategy 2: ODBC + Admin ────────────────────────────────
print("\n[2] ODBC + Uid=Admin;Pwd=")
try:
    c = pyodbc.connect(f"Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={path};Uid=Admin;Pwd=;")
    print("    SUCCESS")
    c.close()
except Exception as e:
    print(f"    FAIL: {e}")

# ── Strategy 3: ADODB ACE ────────────────────────────────────
print("\n[3] ADODB Microsoft.ACE.OLEDB.12.0")
try:
    conn = w.Dispatch("ADODB.Connection")
    conn.ConnectionString = f"Provider=Microsoft.ACE.OLEDB.12.0;Data Source={path};Persist Security Info=False;"
    conn.Open()
    print("    SUCCESS")
    conn.Close()
except Exception as e:
    print(f"    FAIL: {e}")

# ── Strategy 4: ADODB Jet ────────────────────────────────────
print("\n[4] ADODB Microsoft.Jet.OLEDB.4.0")
try:
    conn = w.Dispatch("ADODB.Connection")
    conn.ConnectionString = f"Provider=Microsoft.Jet.OLEDB.4.0;Data Source={path};Persist Security Info=False;"
    conn.Open()
    print("    SUCCESS")
    conn.Close()
except Exception as e:
    print(f"    FAIL: {e}")

# ── Strategy 5: ADODB ACE + Admin user ──────────────────────
print("\n[5] ADODB ACE + User Id=Admin")
try:
    conn = w.Dispatch("ADODB.Connection")
    conn.ConnectionString = f"Provider=Microsoft.ACE.OLEDB.12.0;Data Source={path};User Id=admin;Password=;"
    conn.Open()
    print("    SUCCESS")
    conn.Close()
except Exception as e:
    print(f"    FAIL: {e}")

# ── File header check ────────────────────────────────────────
print("\n[File header]")
try:
    with open(path, "rb") as f:
        header = f.read(16)
    print(f"    First 16 bytes: {header.hex()}")
    if header[:4] == b'\x00\x01\x00\x00':
        print("    -> Jet 3.x format (Access 95/97) — ACE driver does NOT support this")
    elif header[:4] == b'\x00\x01\x00\x00':
        print("    -> Jet 4.0 format (Access 2000+)")
    elif header[4:8] == b'Stan':
        print("    -> Standard Jet signature detected")
    else:
        print("    -> Unknown/encrypted header")
except Exception as e:
    print(f"    FAIL reading file: {e}")

print(f"\n{'='*60}")
