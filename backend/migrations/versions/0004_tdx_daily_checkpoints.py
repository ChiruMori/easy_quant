"""通达信单日增量检查点，与行情写入同事务。"""

import sqlalchemy as sa
from alembic import op

revision = "0004_tdx_daily_checkpoints"
down_revision = "0003_history_coverage_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    if inspector is None or "tdx_daily_checkpoints" not in inspector.get_table_names():
        op.create_table(
            "tdx_daily_checkpoints",
            sa.Column("trading_day", sa.Date(), primary_key=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("archive_sha256", sa.String(64)),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("checked_at", sa.DateTime(), nullable=False),
            sa.Column("reason", sa.String(200), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("tdx_daily_checkpoints")
