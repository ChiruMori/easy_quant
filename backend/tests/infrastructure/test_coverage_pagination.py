from typing import cast

from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from easy_quant.infrastructure.persistence.repositories.runtime import SqlAlchemyMarketDataStore


class PageSession:
    def __init__(self) -> None:
        self.page_queries = []
        self.scalar_queries = []

    def scalar(self, query):
        self.scalar_queries.append(query)
        return 6001

    def scalars(self, query):
        self.page_queries.append(query)
        return []


def test_page_jump_skips_only_primary_keys_and_cursor_pages_avoid_offset() -> None:
    session = PageSession()
    store = SqlAlchemyMarketDataStore(cast(Session, session))

    store.coverage_page(page=120, page_size=50)
    jump_sql = str(session.page_queries.pop().compile(dialect=mysql.dialect()))
    assert "SELECT instruments.symbol" in jump_sql
    assert "instruments.name" not in jump_sql
    assert "LIMIT %s, %s" in jump_sql

    store.coverage_page(page=121, page_size=50, after_symbol="005999")
    next_sql = str(session.page_queries.pop().compile(dialect=mysql.dialect()))
    assert "instruments.symbol >" in next_sql
    assert "LIMIT %s, %s" not in next_sql

    store.coverage_page(page=119, page_size=50, before_symbol="005950")
    previous_sql = str(session.page_queries.pop().compile(dialect=mysql.dialect()))
    assert "instruments.symbol <" in previous_sql
    assert "ORDER BY instruments.symbol DESC" in previous_sql
    assert "LIMIT %s, %s" not in previous_sql

    store.coverage_page(page=2, page_size=50, status="完全同步", after_symbol="000049")
    filtered_sql = str(session.page_queries.pop().compile(dialect=mysql.dialect()))
    assert "min(daily_bars.trading_day)" in filtered_sql
    assert "max(daily_bars.trading_day)" in filtered_sql
    assert "GROUP BY daily_bars.symbol" in filtered_sql
    assert "count(daily_bars" not in filtered_sql
    assert "LIMIT %s, %s" not in filtered_sql
