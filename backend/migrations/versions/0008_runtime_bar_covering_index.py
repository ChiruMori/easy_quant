"""为策略运行提供按交易日读取 OHLC 的覆盖索引。"""

import sqlalchemy as sa
from alembic import op

revision = "0008_runtime_bar_covering_index"
down_revision = "0007_daily_bar_day_index"
branch_labels = None
depends_on = None


def _indexes() -> set[str]:
    if op.get_context().as_sql:
        return set()
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("daily_bars")}


def upgrade() -> None:
    indexes = _indexes()
    if "ix_daily_bars_runtime_day" not in indexes:
        op.create_index(
            "ix_daily_bars_runtime_day",
            "daily_bars",
            ["trading_day", "symbol", "available_at", "open", "high", "low", "close"],
        )
    if "ix_daily_bars_day_symbol" in indexes or op.get_context().as_sql:
        op.drop_index("ix_daily_bars_day_symbol", table_name="daily_bars")


def downgrade() -> None:
    indexes = _indexes()
    if "ix_daily_bars_day_symbol" not in indexes:
        op.create_index("ix_daily_bars_day_symbol", "daily_bars", ["trading_day", "symbol"])
    if "ix_daily_bars_runtime_day" in indexes or op.get_context().as_sql:
        op.drop_index("ix_daily_bars_runtime_day", table_name="daily_bars")
