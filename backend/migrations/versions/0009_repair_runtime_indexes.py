"""撤销宽运行索引，保留现有窄日期索引与覆盖统计索引。"""

import sqlalchemy as sa
from alembic import op

revision = "0009_repair_runtime_indexes"
down_revision = "0008_runtime_bar_covering_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().as_sql:
        # 离线 SQL 不能探测中断 DDL 状态，禁止盲目生成清理语句。
        raise RuntimeError("此迁移需要在线检查现有索引")
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("daily_bars")}
    if "ix_daily_bars_day_symbol" not in indexes:
        op.create_index("ix_daily_bars_day_symbol", "daily_bars", ["trading_day", "symbol"])
    if "ix_daily_bars_runtime_day" in indexes:
        op.drop_index("ix_daily_bars_runtime_day", table_name="daily_bars")


def downgrade() -> None:
    # 错误的宽索引不应在回退时重建。
    pass
