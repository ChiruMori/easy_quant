"""策略草稿、单向生命周期与版本元数据；无新增外键。"""

import sqlalchemy as sa
from alembic import op

revision = "0013_strategy_workspace"
down_revision = "0012_resource_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {row["name"] for row in inspector.get_columns("strategy_versions")}
    for column in (
        sa.Column("state", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("name", sa.String(160), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    ):
        if column.name not in columns:
            op.add_column("strategy_versions", column)
    if "next_version_number" not in {row["name"] for row in inspector.get_columns("strategies")}:
        op.add_column(
            "strategies",
            sa.Column("next_version_number", sa.Integer(), nullable=False, server_default="1"),
        )
    op.execute("""UPDATE strategy_versions v JOIN strategies s ON s.id = v.strategy_id
        SET v.name = s.name, v.description = COALESCE(s.description, '') WHERE v.name = ''""")
    op.execute("""UPDATE strategies s SET next_version_number = GREATEST(next_version_number,
        COALESCE((SELECT MAX(v.number) + 1 FROM strategy_versions v
                  WHERE v.strategy_id = s.id), 1))""")
    op.execute("""UPDATE strategy_versions v SET state = 'testing' WHERE state = 'draft'
        AND EXISTS (SELECT 1 FROM backtest_runs b WHERE b.strategy_version_id = v.id)""")
    op.execute("""UPDATE strategy_versions v SET state = 'live' WHERE EXISTS (
        SELECT 1 FROM runtime_documents d WHERE d.namespace = 'live_instances'
        AND JSON_UNQUOTE(JSON_EXTRACT(d.payload_json, '$.strategy_version_id')) = v.id)
        OR EXISTS (SELECT 1 FROM live_instances l WHERE l.strategy_version_id = v.id)""")


def downgrade():
    # 保留已锁定状态，不在降级时重新开放历史代码编辑。
    pass
