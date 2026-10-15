"""只读、限时数据库诊断；输出不含连接身份、任务载荷和 SQL 原文。"""

import json
from time import perf_counter

import pymysql
from sqlalchemy.engine import make_url

from easy_quant.config import get_settings

QUERIES = {
    "transactions": """SELECT trx_id,trx_state,trx_started,trx_mysql_thread_id,
        trx_rows_locked,trx_rows_modified,trx_isolation_level FROM information_schema.innodb_trx""",
    "lock_waits": """SELECT w.requesting_trx_id,w.blocking_trx_id,l.lock_table,
        l.lock_index,l.lock_type,l.lock_mode FROM information_schema.innodb_lock_waits w
        JOIN information_schema.innodb_locks l ON l.lock_id=w.requested_lock_id""",
    "process_states": """SELECT id,command,time,state FROM information_schema.processlist
        WHERE db=DATABASE()""",
    "table_sizes": """SELECT table_name,table_rows,data_length,index_length,data_free
        FROM information_schema.tables WHERE table_schema=DATABASE()
        AND table_name IN ('daily_bars','jobs','backtest_runs')""",
    "bar_columns": """SELECT column_name,column_type,is_nullable FROM information_schema.columns
        WHERE table_schema=DATABASE() AND table_name='daily_bars' ORDER BY ordinal_position""",
    "bar_indexes": """SELECT index_name,seq_in_index,column_name,cardinality
        FROM information_schema.statistics WHERE table_schema=DATABASE()
        AND table_name='daily_bars' ORDER BY index_name,seq_in_index""",
    "index_sizes": """SELECT index_name,stat_value*@@innodb_page_size AS bytes
        FROM mysql.innodb_index_stats WHERE database_name=DATABASE()
        AND table_name='daily_bars' AND stat_name='size'""",
    "job_counts": "SELECT status,COUNT(*) AS count FROM jobs GROUP BY status",
    "version": "SELECT version_num FROM alembic_version",
    "settings": """SELECT @@tx_isolation AS isolation_level,
        @@innodb_buffer_pool_size AS buffer_pool_bytes,
        @@innodb_lock_wait_timeout AS lock_wait_seconds,
        @@innodb_file_per_table AS file_per_table""",
    "bounds_plan": """EXPLAIN SELECT symbol,MIN(trading_day),MAX(trading_day)
        FROM daily_bars FORCE INDEX(ix_daily_bars_coverage) GROUP BY symbol""",
    "statement_shapes": """SELECT t.PROCESSLIST_ID,s.DIGEST_TEXT
        FROM performance_schema.events_statements_current s
        JOIN performance_schema.threads t ON t.THREAD_ID=s.THREAD_ID
        WHERE t.PROCESSLIST_DB=DATABASE()""",
    "bounded_bar_sample": """SELECT COUNT(*) AS sampled_rows,
        AVG(OCTET_LENGTH(source)) AS source_bytes,AVG(OCTET_LENGTH(adjustment)) AS adjustment_bytes,
        AVG(COALESCE(OCTET_LENGTH(archive_sha256),0)) AS archive_bytes,
        COUNT(DISTINCT archive_sha256) AS archive_distinct,COUNT(DISTINCT source) AS source_distinct
        FROM (SELECT p.source,p.adjustment,p.archive_sha256
        FROM daily_bars b FORCE INDEX(PRIMARY)
        LEFT JOIN bar_provenance p ON p.id=b.provenance_id
        WHERE b.symbol IN ('000001','000002','600000','600519','300001')
        AND b.trading_day>='2026-09-01' AND b.trading_day<'2026-10-01' LIMIT 1000) s""",
    "runtime_plan": """EXPLAIN SELECT symbol,trading_day,available_at,open,high,low,close
        FROM daily_bars FORCE INDEX(PRIMARY)
        WHERE symbol IN ('000001','000002','600000','600519','300001')
        AND trading_day>='2026-09-01' AND trading_day<'2026-10-01' ORDER BY symbol,trading_day""",
    "coverage_plan": """EXPLAIN SELECT symbol,MIN(trading_day),MAX(trading_day),COUNT(*)
        FROM daily_bars FORCE INDEX(ix_daily_bars_coverage) GROUP BY symbol""",
}


def main():
    url = make_url(get_settings().database_url.get_secret_value())
    connection = pymysql.connect(
        host=url.host or "localhost",
        port=url.port or 3306,
        user=url.username,
        password=url.password,
        database=url.database,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        read_timeout=8,
        write_timeout=8,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("SET SESSION max_statement_time=5")
            for name, sql in QUERIES.items():
                started = perf_counter()
                try:
                    cursor.execute(sql)
                    rows = cursor.fetchall()
                    print(
                        json.dumps(
                            {
                                "query": name,
                                "seconds": round(perf_counter() - started, 3),
                                "rows": rows,
                            },
                            default=str,
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                except pymysql.MySQLError as error:
                    print(
                        json.dumps({"query": name, "error_code": error.args[0]}, default=str),
                        flush=True,
                    )
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
