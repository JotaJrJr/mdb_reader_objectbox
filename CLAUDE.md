# MDB Reader — Project Spec

## Overview
Desktop executable that opens Microsoft Access `.mdb` files with a table browser and SQL query editor.

## Stack Decisions (locked)

| Concern | Choice | Reason |
|---------|--------|--------|
| GUI framework | PyQt6 | Native Windows look, drag-drop, QTableView, QSyntaxHighlighter |
| MDB access (primary) | pyodbc + ACE ODBC driver | Full SQL support, best Windows compatibility |
| MDB access (fallback) | mdb-parser (pure Python) | Schema-only read when no ODBC driver installed |
| Testing | pytest + pytest-qt | TDD, UI widget tests |
| Packaging | PyInstaller | Single .exe output |

## Architecture

```
mdb_reader/
├── core/
│   ├── connection.py     # MDBConnection — open/close/execute
│   ├── schema.py         # TableMeta — columns, row count, indexes, PKs
│   └── diagnostics.py    # Error → human-readable fix (driver missing, password, MDW, etc.)
├── ui/
│   ├── main_window.py    # MainWindow + drag-drop
│   ├── sidebar.py        # QTreeWidget — tables list + click details
│   ├── editor.py         # SQL editor + execute button + results
│   └── results.py        # QTableView + row count label
├── tests/
│   ├── conftest.py       # fixtures: temp .mdb, mock connection
│   ├── test_connection.py
│   ├── test_schema.py
│   ├── test_diagnostics.py
│   └── test_ui.py
├── main.py               # entry point
├── requirements.txt
└── .pre-commit-config.yaml
```

## TDD Rules (non-negotiable)
1. Write test first — no production code without a failing test
2. Red → Green → Refactor cycle
3. Pre-commit hook runs `pytest -q --tb=short` — commit blocked if any test fails
4. Minimum coverage target: core/ modules at 90%

## MDB Security Layers (must handle)
| Layer | Detection | User message |
|-------|-----------|--------------|
| No ODBC driver | `IM002` ODBC error | Install Microsoft Access Database Engine 2016 (link) |
| File-level password | `28000` / `42000` | File is password-protected — enter password or contact owner |
| Workgroup security (MDW) | `28000` with `(3029)` | Requires `.mdw` workgroup file — contact database admin |
| File locked / exclusive | `(3045)` | File open exclusively by another process — close MS Access |
| 64/32-bit mismatch | `IM014` | Need 32-bit or 64-bit ACE driver matching Python bitness |

## UI Behavior
- Startup: empty state, large drop target, "Open or drop .mdb file"
- After open: sidebar shows table list; click table → panel shows row count, columns, types, indexes
- Main panel: SQL editor, Execute button (F5), results in QTableView with row count
- Error state: red banner with diagnostic message + fix steps

## What's Not Scope
- Write/INSERT/UPDATE/DELETE support (read-only for now)
- .accdb support (future, same driver works)
- Non-Windows OS (Linux/Mac needs mdbtools, different driver path)
