"""全市场历史覆盖统计使用较小的二级索引。"""

import sqlalchemy as sa
from alembic import op

revision = "0003_history_coverage_index"
down_revision = "0002_history_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("daily_bars")} if inspector else set()
    if "ix_daily_bars_coverage" not in indexes:
        op.create_index("ix_daily_bars_coverage", "daily_bars", ["symbol", "trading_day"])


def downgrade() -> None:
    op.drop_index("ix_daily_bars_coverage", table_name="daily_bars")
