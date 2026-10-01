from __future__ import annotations

import tempfile
from collections.abc import Iterable
from datetime import UTC
from pathlib import Path

from pymysql import MySQLError
from sqlalchemy.orm import Session

from easy_quant.domain.market_data.history import HistoryBar

LOAD_SQL = (
    "LOAD DATA LOCAL INFILE %s REPLACE INTO TABLE daily_bars CHARACTER SET ascii "
    "FIELDS TERMINATED BY '\\t' LINES TERMINATED BY '\\n' "
    "(symbol,trading_day,open,high,low,close,volume,amount,available_at) "
    "SET source='tdx-official',adjustment='none',archive_sha256=%s"
)


def tsv_lines(bars: Iterable[HistoryBar]) -> Iterable[str]:
    for bar in bars:
        # 日期和数字来自已验证值对象；不接受用户自定义分隔符或 SQL 字段。
        fields = [bar.symbol, bar.trading_day.isoformat()]
        fields.extend(
            format(value, "f")
            for value in (bar.open, bar.high, bar.low, bar.close, bar.volume, bar.amount)
        )
        fields.append(bar.available_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"))
        yield "\t".join(fields) + "\n"


class LocalFileHistoryLoader:
    """仅管理员 CLI 显式启用的原生批量写入；临时文件不进入 Git。"""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def __call__(self, session: Session, bars: list[HistoryBar], digest: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="ascii", dir=self.directory, suffix=".tsv", delete=False
        ) as stream:
            path = Path(stream.name)
            stream.writelines(tsv_lines(bars))
        try:
            cursor = session.connection().connection.cursor()
            try:
                cursor.execute(LOAD_SQL, (str(path.resolve()), digest))
                cursor.execute("SHOW WARNINGS LIMIT 1")
                warning = cursor.fetchone()
                if warning is not None:
                    raise RuntimeError(f"原生批量导入出现数据库警告（{warning[1]}），事务已回滚")
            finally:
                cursor.close()
        except MySQLError as error:
            raise RuntimeError(f"原生批量导入失败（{type(error).__name__}），事务已回滚") from None
        finally:
            path.unlink(missing_ok=True)
