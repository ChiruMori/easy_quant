"""真实SQL编译器与驱动转义，底层查询截获；不建立数据库连接。"""

from typing import cast

from pymysql import Connection
from pymysql.cursors import Cursor
from sqlalchemy.dialects.mysql import pymysql
from sqlalchemy.orm import Session

from easy_quant.infrastructure.persistence.repositories.runtime import SqlAlchemyMarketDataStore


def test_instrument_upsert_binds_case_parameters_before_sending_to_pymysql():
    sent = []

    class OfflineConnection(Connection):
        # 模拟握手后的标志，仅供驱动本地转义；从不建立连接。
        server_status = 0

    connection = OfflineConnection(defer_connect=True)

    class CapturingCursor(Cursor):
        def _query(self, query):
            text = query.decode("utf8") if isinstance(query, (bytes, bytearray)) else query
            assert "%(" not in text, "批量后缀的CASE参数尚未绑定，会导致MariaDB 1064"
            sent.append(text)
            self.rowcount = 2

    cursor = CapturingCursor(connection)

    class SessionFake:
        def execute(self, statement, rows=None):
            compiled = statement.compile(dialect=pymysql.dialect(paramstyle="pyformat"))
            if rows is not None:
                cursor.executemany(
                    str(compiled),
                    [{**compiled.params, **row} for row in rows],
                )
            else:
                cursor.execute(str(compiled), compiled.params)

        def commit(self):
            pass

        def expire_all(self):
            pass

    SqlAlchemyMarketDataStore(cast(Session, SessionFake())).upsert_instruments(
        [
            {"symbol": "000001", "name": "测试'证券", "exchange": "深交所"},
            {
                "symbol": "000002",
                "exchange": "深交所",
                "listed_on": "1991-01-29",
                "status": "suspended",
            },
        ]
    )
    assert len(sent) == 1
    assert "CASE WHEN" in sent[0] and "'suspended'" in sent[0] and "'active'" in sent[0]
    assert "coalesce(VALUES(listed_on), instruments.listed_on)" in sent[0]
    assert "NULL" in sent[0] and "1991-01-29" in sent[0]
