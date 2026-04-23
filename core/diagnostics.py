from dataclasses import dataclass
from typing import List

from core.connection import MDBAccessError


@dataclass
class Diagnostic:
    title: str
    steps: List[str]
    severity: str  # "error" | "warning"


_DIAGNOSTICS = {
    "DRIVER_MISSING": Diagnostic(
        title="Microsoft Access ODBC Driver Not Installed",
        severity="error",
        steps=[
            "Download and install 'Microsoft Access Database Engine 2016 Redistributable'.",
            "Download from: https://www.microsoft.com/en-us/download/details.aspx?id=54920",
            "Choose the same bitness (32 or 64-bit) as your Python installation.",
            "Restart this application after installation.",
        ],
    ),
    "PASSWORD_REQUIRED": Diagnostic(
        title="File is Password-Protected",
        severity="error",
        steps=[
            "This .mdb file requires a password to open.",
            "Enter the correct password when prompted, or contact the database owner.",
            "If you don't know the password, the file contents cannot be accessed.",
        ],
    ),
    "WORKGROUP_SECURITY": Diagnostic(
        title="Workgroup Security (.mdw) Required",
        severity="error",
        steps=[
            "This database uses Microsoft Access workgroup security.",
            "A matching workgroup file (.mdw) is required to authenticate.",
            "Contact your database administrator for the workgroup file and credentials.",
            "Copy the .mdw file to a known location and provide it when prompted.",
        ],
    ),
    "FILE_LOCKED": Diagnostic(
        title="File is Locked by Another Process",
        severity="error",
        steps=[
            "Another application has opened this .mdb file in exclusive mode.",
            "Close Microsoft Access or any other application using this file.",
            "If the file is on a network share, check that no remote user has it open.",
            "Try again after closing all other applications that use the file.",
        ],
    ),
    "BITNESS_MISMATCH": Diagnostic(
        title="32/64-bit Driver Mismatch",
        severity="error",
        steps=[
            "The installed ACE ODBC driver bitness does not match your Python installation.",
            "Check your Python bitness: run 'python -c \"import struct; print(struct.calcsize(chr(80))*8)\"'",
            "Download the matching Access Database Engine (32-bit or 64-bit) from Microsoft.",
            "Uninstall the mismatched driver before installing the correct one.",
        ],
    ),
    "QUERY_ERROR": Diagnostic(
        title="SQL Query Error",
        severity="warning",
        steps=[
            "The query contains a syntax error or references an invalid table/column.",
            "Check for typos in table and column names (Access SQL is case-insensitive).",
            "Use square brackets around names with spaces: [My Table].[My Column]",
            "Access SQL does not support all standard SQL features (e.g., no FULL OUTER JOIN).",
        ],
    ),
    "REGISTRY_PERMISSION": Diagnostic(
        title="Registry Permission Error — Run as Administrator",
        severity="error",
        steps=[
            "The Access ODBC driver needs write access to the Windows registry (HKLM\\SOFTWARE\\ODBC).",
            "Fix: right-click the app (or Python) and choose 'Run as Administrator'.",
            "Alternative: grant your user write access to HKLM\\SOFTWARE\\ODBC\\ODBC.INI in regedit.",
            "If the file is very old (pre-Access 97 / Jet 3.x), the ACE driver does not support it.",
        ],
    ),
    "FILE_CORRUPT": Diagnostic(
        title="File May Be Corrupted or Unrecognized Format",
        severity="error",
        steps=[
            "The file could not be read as a valid .mdb database.",
            "It may be corrupted, encrypted, or in an unsupported format.",
            "Try opening it with Microsoft Access — if it fails there too, the file is damaged.",
            "If the file opens in Access, compact it (Database Tools > Compact and Repair) then retry.",
        ],
    ),
    "UNKNOWN": Diagnostic(
        title="Unexpected Error",
        severity="error",
        steps=[
            "An unexpected error occurred while accessing the file.",
            "Verify the file is a valid .mdb file and is not corrupted.",
            "Try opening it with Microsoft Access to check for internal errors.",
            "Check Windows Event Viewer for additional ODBC error details.",
        ],
    ),
}


def diagnose(error: MDBAccessError) -> Diagnostic:
    base = _DIAGNOSTICS.get(error.error_code, _DIAGNOSTICS["UNKNOWN"])
    # Always append raw driver error so user can see exact message
    raw = str(error).strip()
    if raw and raw not in base.steps:
        return Diagnostic(
            title=base.title,
            steps=list(base.steps) + [f"Driver detail: {raw}"],
            severity=base.severity,
        )
    return base
