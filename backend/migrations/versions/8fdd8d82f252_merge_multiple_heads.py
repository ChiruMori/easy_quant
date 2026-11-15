"""合并回测名称与财报记录迁移分支，不执行额外DDL。"""

revision = "8fdd8d82f252"
down_revision = ("0015_backtest_name", "0015_financial_records")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
