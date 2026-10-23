"""独立存储可编辑回测名，避免 worker 写结果覆盖名称。"""

import sqlalchemy as sa
from alembic import op

revision = "0015_backtest_name"
down_revision = "0014_index_daily_schedule"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("backtest_runs", sa.Column("name", sa.String(160), nullable=True))


def downgrade():
    op.drop_column("backtest_runs", "name")
