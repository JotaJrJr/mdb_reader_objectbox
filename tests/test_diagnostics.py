import pytest
from core.connection import MDBAccessError
from core.diagnostics import Diagnostic, diagnose


def _make_error(code: str, msg: str = "") -> MDBAccessError:
    return MDBAccessError(error_code=code, message=msg or code)


class TestDiagnosticModel:
    def test_has_title_and_steps(self):
        d = Diagnostic(title="Some problem", steps=["Do this", "Then that"], severity="error")
        assert d.title == "Some problem"
        assert len(d.steps) == 2
        assert d.severity == "error"


class TestDiagnose:
    def test_driver_missing_has_download_step(self):
        err = _make_error("DRIVER_MISSING")
        diag = diagnose(err)
        assert diag.severity == "error"
        assert any("Access Database Engine" in s for s in diag.steps)
        assert any("microsoft.com" in s.lower() or "download" in s.lower() for s in diag.steps)

    def test_password_required_has_password_step(self):
        err = _make_error("PASSWORD_REQUIRED")
        diag = diagnose(err)
        assert diag.severity == "error"
        assert any("password" in s.lower() for s in diag.steps)

    def test_workgroup_security_mentions_mdw(self):
        err = _make_error("WORKGROUP_SECURITY")
        diag = diagnose(err)
        assert any(".mdw" in s or "workgroup" in s.lower() for s in diag.steps)

    def test_file_locked_mentions_close(self):
        err = _make_error("FILE_LOCKED")
        diag = diagnose(err)
        assert any("close" in s.lower() or "access" in s.lower() for s in diag.steps)

    def test_bitness_mismatch_gives_bitness_instructions(self):
        err = _make_error("BITNESS_MISMATCH")
        diag = diagnose(err)
        assert any("32" in s or "64" in s or "bit" in s.lower() for s in diag.steps)

    def test_query_error_shows_message(self):
        err = _make_error("QUERY_ERROR", "QUERY_ERROR: unexpected token near FROM")
        diag = diagnose(err)
        assert diag.severity == "warning"
        assert any("syntax" in s.lower() or "query" in s.lower() for s in diag.steps)

    def test_unknown_error_returns_generic_diagnostic(self):
        err = _make_error("UNKNOWN", "Something unexpected happened")
        diag = diagnose(err)
        assert diag.severity == "error"
        assert len(diag.steps) >= 1

    def test_all_error_codes_have_diagnostics(self):
        codes = ["DRIVER_MISSING", "PASSWORD_REQUIRED", "WORKGROUP_SECURITY",
                 "FILE_LOCKED", "BITNESS_MISMATCH", "QUERY_ERROR", "UNKNOWN"]
        for code in codes:
            err = _make_error(code)
            diag = diagnose(err)
            assert diag is not None, f"No diagnostic for {code}"
            assert diag.title, f"Empty title for {code}"
            assert diag.steps, f"Empty steps for {code}"
