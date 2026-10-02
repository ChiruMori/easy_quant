"""扩大后台任务、回测详情和策略源码的容量。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT

revision = "0005_large_run_payloads"
down_revision = "0004_tdx_daily_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, column in (
        ("jobs", "result_json"),
        ("jobs", "error_json"),
        ("backtest_runs", "payload_json"),
        ("strategy_versions", "source_code"),
    ):
        op.alter_column(
            table, column, existing_type=sa.Text(), type_=LONGTEXT(), existing_nullable=False
        )


def downgrade() -> None:
    for table, column in (
        ("jobs", "result_json"),
        ("jobs", "error_json"),
        ("backtest_runs", "payload_json"),
        ("strategy_versions", "source_code"),
    ):
        op.alter_column(
            table, column, existing_type=LONGTEXT(), type_=sa.Text(), existing_nullable=False
        )
