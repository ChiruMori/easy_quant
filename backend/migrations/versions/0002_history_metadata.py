"""日线数据口径、来源与全量导入检查点。"""

import sqlalchemy as sa
from alembic import op

revision = "0002_history_metadata"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 增量迁移保留已有行情；按字段检查也支持 DDL 部分成功后的安全重试。
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = (
        {column["name"] for column in inspector.get_columns("daily_bars")} if inspector else set()
    )
    for column in (
        sa.Column("amount", sa.Numeric(28, 4), nullable=True),
        sa.Column("source", sa.String(40), server_default="unknown", nullable=False),
        sa.Column("adjustment", sa.String(20), server_default="unknown", nullable=False),
        sa.Column("archive_sha256", sa.String(64), nullable=True),
    ):
        if column.name not in existing:
            op.add_column("daily_bars", column)
    if inspector is None or not inspector.has_table("history_import_stocks"):
        op.create_table(
            "history_import_stocks",
            sa.Column("archive_sha256", sa.String(64), primary_key=True),
            sa.Column("symbol", sa.String(20), primary_key=True),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("first_day", sa.Date(), nullable=False),
            sa.Column("last_day", sa.Date(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("history_import_stocks")
    for name in ("archive_sha256", "adjustment", "source", "amount"):
        op.drop_column("daily_bars", name)
