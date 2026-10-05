from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy.orm import sessionmaker

from easy_quant.infrastructure.persistence import session as persistence_session
from easy_quant.infrastructure.persistence.session import create_scoped_session


def test_concurrent_threads_use_distinct_sessions_without_storage() -> None:
    sessions = create_scoped_session(sessionmaker())
    barrier = Barrier(2)

    def get_thread_session():
        first = sessions()
        try:
            barrier.wait(timeout=5)
            return first, sessions()
        finally:
            sessions.remove()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: get_thread_session(), range(2)))
    assert results[0][0] is results[0][1]
    assert results[1][0] is results[1][1]
    assert results[0][0] is not results[1][0]


def test_releasing_scope_discards_the_previous_session() -> None:
    sessions = create_scoped_session(sessionmaker())
    first = sessions()
    sessions.remove()
    try:
        assert sessions() is not first
    finally:
        sessions.remove()


def test_database_errors_hide_bound_parameters(monkeypatch) -> None:
    options = {}

    def fake_create_engine(_url, **kwargs):
        options.update(kwargs)
        return object()

    monkeypatch.setattr(persistence_session, "create_engine", fake_create_engine)
    persistence_session.create_database_engine("mysql+pymysql://unused/db")
    assert options["hide_parameters"] is True
