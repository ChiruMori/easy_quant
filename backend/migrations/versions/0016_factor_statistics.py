"""因子调用统计与幂等回执，无外键。"""

import sqlalchemy as sa
from alembic import op

revision = "0016_factor_statistics"
down_revision = "8fdd8d82f252"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "factor_statistics",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("calls", sa.BigInteger(), nullable=False),
        sa.Column("elapsed_ns", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "factor_statistic_receipts", sa.Column("event_id", sa.String(36), primary_key=True)
    )


def downgrade():
    op.drop_table("factor_statistic_receipts")
    op.drop_table("factor_statistics")
