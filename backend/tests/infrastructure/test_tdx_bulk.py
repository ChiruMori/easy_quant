import io
from pathlib import Path
from typing import cast

import pytest
from pymysql import OperationalError
from sqlalchemy.orm import Session

from easy_quant.infrastructure.imports import tdx_bulk
from easy_quant.infrastructure.imports.tdx import parse_day
from easy_quant.infrastructure.imports.tdx_bulk import LOAD_SQL, LocalFileHistoryLoader, tsv_lines
from tests.infrastructure.test_tdx_archive import fixture_bytes


def test_bulk_rows_keep_prices_units_and_utc_availability() -> None:
    lines = list(tsv_lines(parse_day(fixture_bytes(), "000001")))
    assert (
        lines[0] == "000001\t2026-09-29\t10\t11\t9\t10.5\t1000\t12345.5000\t2026-09-29 07:00:00\n"
    )
    assert len(lines) == 2
    assert "archive_sha256=%s" in LOAD_SQL
    assert "adjustment='none'" in LOAD_SQL


@pytest.mark.parametrize("failure", ["warning", "db-error", None])
def test_native_loader_checks_warnings_redacts_errors_and_removes_owned_file(monkeypatch, failure):
    state = {"closed": False, "removed": False}

    class MemoryFile(io.StringIO):
        name = "internal.tsv"

    class MemoryPath:
        def __init__(self, _name=""):
            pass

        def mkdir(self, **_kwargs):
            pass

        def resolve(self):
            return "internal.tsv"

        def unlink(self, **_kwargs):
            state["removed"] = True

    class Cursor:
        def execute(self, _sql, *_args):
            if failure == "db-error":
                raise OperationalError(1234, "SECRET_CONNECTION_DETAIL")

        def fetchone(self):
            return ("Note", 1265, "SECRET_DETAIL") if failure == "warning" else None

        def close(self):
            state["closed"] = True

    class Connection:
        @property
        def connection(self):
            return self

        def cursor(self):
            return Cursor()

    class FakeSession:
        def connection(self):
            return Connection()

    monkeypatch.setattr(tdx_bulk.tempfile, "NamedTemporaryFile", lambda **_kwargs: MemoryFile())
    monkeypatch.setattr(tdx_bulk, "Path", MemoryPath)
    loader = LocalFileHistoryLoader(cast(Path, MemoryPath()))
    if failure:
        with pytest.raises(RuntimeError) as error:
            loader(cast(Session, FakeSession()), parse_day(fixture_bytes(), "000001"), "a" * 64)
        assert "SECRET" not in str(error.value)
        assert "事务已回滚" in str(error.value)
    else:
        loader(cast(Session, FakeSession()), parse_day(fixture_bytes(), "000001"), "a" * 64)
    assert state == {"closed": True, "removed": True}
