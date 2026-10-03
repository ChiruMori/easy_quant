import gzip
import random
from typing import cast

from sqlalchemy import Table
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from easy_quant.infrastructure.persistence.models.backtesting import BacktestRunModel
from easy_quant.infrastructure.persistence.models.scheduling import JobModel
from easy_quant.infrastructure.persistence.models.strategies import StrategyVersionModel
from easy_quant.infrastructure.persistence.repositories.runtime import snapshot_chunks


def test_large_run_columns_use_mysql_longtext() -> None:
    for model, column in (
        (JobModel, "result_json"),
        (JobModel, "error_json"),
        (BacktestRunModel, "payload_json"),
        (StrategyVersionModel, "source_code"),
    ):
        ddl = str(CreateTable(cast(Table, model.__table__)).compile(dialect=mysql.dialect()))
        assert f"{column} LONGTEXT" in ddl


def test_prefixed_job_identifier_fits_mysql_column() -> None:
    ddl = str(CreateTable(cast(Table, JobModel.__table__)).compile(dialect=mysql.dialect()))
    assert "id VARCHAR(64) NOT NULL" in ddl
    assert len("job-" + "00000000-0000-0000-0000-000000000000") <= 64


def test_snapshot_chunks_fit_blob_limit_and_reassemble() -> None:
    payload = random.Random(20261002).randbytes(160_000)
    chunks = snapshot_chunks(payload)
    assert len(chunks) >= 3
    assert all(0 < len(chunk) <= 60_000 for chunk in chunks)
    assert gzip.decompress(b"".join(chunks)) == payload
