"""支持按交易日范围读取快测与回测行情。"""

from alembic import op

revision = "0007_daily_bar_day_index"
down_revision = "0006_job_identifier_length"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_daily_bars_day_symbol", "daily_bars", ["trading_day", "symbol"])


def downgrade() -> None:
    op.drop_index("ix_daily_bars_day_symbol", table_name="daily_bars")
