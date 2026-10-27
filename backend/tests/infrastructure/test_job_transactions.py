from datetime import timedelta
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.domain.scheduling.entities import Job
from easy_quant.infrastructure.persistence.repositories.jobs import SqlAlchemyJobRepository


class JobSession:
    def __init__(self, row=None, *, fail=False):
        self.row, self.fail = row, fail
        self.commits = self.rollbacks = self.closes = 0
        self.statements = []
        self.isolation = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closes += 1

    def connection(self, *, execution_options):
        self.isolation = execution_options["isolation_level"]

    def scalar(self, query):
        self.statements.append(query)
        if self.fail:
            raise RuntimeError("fake database failure")
        return self.row

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_idle_poll_finishes_its_transaction_and_closes_session(fixed_now):
    session = JobSession()
    repository = SqlAlchemyJobRepository(cast(Session, object()), lambda: cast(Session, session))
    assert repository.claim_due("w", fixed_now, fixed_now + timedelta(minutes=5)) is None
    assert session.commits == session.closes == 1
    assert session.isolation == "READ COMMITTED"
    sql = str(session.statements[0].compile(dialect=mysql.dialect()))
    assert "LIMIT" in sql and "FOR UPDATE SKIP LOCKED" in sql
    assert session.statements[0].compile().params["param_1"] == 1


def test_failed_poll_rolls_back_and_releases_locks(fixed_now):
    session = JobSession(fail=True)
    repository = SqlAlchemyJobRepository(cast(Session, object()), lambda: cast(Session, session))
    with pytest.raises(RuntimeError):
        repository.claim_due("w", fixed_now, fixed_now + timedelta(minutes=5))
    assert session.rollbacks == session.closes == 1 and session.commits == 0


def test_idempotent_enqueue_also_releases_its_read_transaction(fixed_now):
    row = SqlAlchemyJobRepository._to_model(Job("j", "demo", "same", {}, fixed_now))
    session = JobSession(row)
    repository = SqlAlchemyJobRepository(cast(Session, object()), lambda: cast(Session, session))
    assert repository.enqueue(Job("other", "demo", "same", {}, fixed_now)).id == "j"
    assert session.commits == session.closes == 1


@pytest.mark.parametrize("operation", ["renew", "finish"])
@pytest.mark.parametrize("affected", [0, 1])
def test_lease_updates_are_fenced_in_an_independent_short_transaction(
    fixed_now, operation, affected
):
    class LeaseSession(JobSession):
        def execute(self, statement):
            self.statements.append(statement)
            return SimpleNamespace(rowcount=affected)

    session = LeaseSession()
    repository = SqlAlchemyJobRepository(cast(Session, object()), lambda: cast(Session, session))
    job = Job("j", "demo", "b", {}, fixed_now)
    job.claim("w", fixed_now, fixed_now + timedelta(minutes=5))
    if operation == "renew":
        accepted = repository.renew_lease("j", "w", 1, fixed_now, fixed_now + timedelta(minutes=5))
    else:
        job.succeed("w", {"ok": True})
        accepted = repository.finish_claim(job, "w", fixed_now)
    assert accepted is bool(affected)
    assert session.commits == session.closes == 1
    sql = str(session.statements[0].compile(dialect=mysql.dialect()))
    where = sql.split("WHERE")[1]
    assert all(
        name in where for name in ["id", "status", "lease_owner", "attempt_count", "lease_until"]
    )
    assert "lease_until >" in where
