"""保留中断版本号；错误的宽索引改由 0009 安全清理。"""

revision = "0008_runtime_bar_covering_index"
down_revision = "0007_daily_bar_day_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 已在部分环境尝试执行旧迁移，但数据库版本仍为 0007；此处不能再建宽索引。
    pass


def downgrade() -> None:
    pass
