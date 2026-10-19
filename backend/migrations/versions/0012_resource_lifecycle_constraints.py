"""删除链路改由业务事务保障，移除相关外键（不删除业务数据）。"""

import sqlalchemy as sa
from alembic import op

revision = "0012_resource_lifecycle"
down_revision = "0011_compact_daily_bars"
branch_labels = None
depends_on = None

TARGETS = {
    "strategies",
    "backtest_runs",
    "live_instances",
    "recommendations",
    "actual_operations",
    "notification_subscriptions",
    "data_snapshots",
}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "resource_lifecycle_mutex" not in inspector.get_table_names():
        op.create_table(
            "resource_lifecycle_mutex", sa.Column("key", sa.String(20), primary_key=True)
        )
    for table in inspector.get_table_names():
        for constraint in inspector.get_foreign_keys(table):
            if constraint["referred_table"] in TARGETS:
                op.drop_constraint(constraint["name"], table, type_="foreignkey")


def downgrade():
    # 迁移后允许业务级联，不能为既有数据盲目重建历史约束。
    pass
