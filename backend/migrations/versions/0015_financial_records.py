"""扩容已有基本面记录并增加按股票查询索引；不接触日线或新增表/外键。"""

import sqlalchemy as sa
from alembic import op

revision = "0015_financial_records"
down_revision = "0014_index_daily_schedule"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "market_records",
        "payload_json",
        existing_type=sa.String(8000),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.add_column("market_records", sa.Column("symbol", sa.String(20), nullable=True))
    op.execute(
        "UPDATE market_records SET symbol = JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.symbol')) "
        "WHERE JSON_VALID(payload_json) AND JSON_EXTRACT(payload_json, '$.symbol') IS NOT NULL"
    )
    op.create_index(
        "ix_market_records_symbol_dataset_at",
        "market_records",
        ["symbol", "dataset_key", "available_at"],
    )


def downgrade():
    op.drop_index("ix_market_records_symbol_dataset_at", table_name="market_records")
    op.drop_column("market_records", "symbol")
    # 保留 TEXT，避免已接入的完整报表回退至8000字节时被截断。
