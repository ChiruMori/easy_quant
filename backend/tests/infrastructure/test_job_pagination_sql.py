from typing import cast

from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.infrastructure.persistence.repositories.jobs import SqlAlchemyJobRepository


def test_job_pagination_limits_database_reads_and_clamps_before_offset():
    statements = []

    class SessionFake:
        def scalar(self, statement):
            statements.append(statement)
            return 45

        def scalars(self, statement):
            statements.append(statement)
            return []

        def commit(self):
            pass

    repository = SqlAlchemyJobRepository(cast(Session, SessionFake()))
    assert repository.list_page(999999999, 20) == ([], 45, 3)
    assert "count(*)" in str(statements[0])
    sql = str(
        statements[1].compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "ORDER BY jobs.available_at DESC, jobs.id DESC" in sql
    assert "LIMIT 40, 20" in sql
