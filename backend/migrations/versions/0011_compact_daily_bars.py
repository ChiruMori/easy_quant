"""日线共享血缘结构基线；保留版本链及空库初始化。"""

import sqlalchemy as sa
from alembic import op

revision = "0011_compact_daily_bars"
down_revision = "0010_expand_raw_cache_blob"
branch_labels = None
depends_on = None


# 固定本 revision 的结构，后续模型演进不能改变历史迁移。
_PROVENANCE_SQL = """CREATE TABLE IF NOT EXISTS bar_provenance (
	id INTEGER UNSIGNED NOT NULL AUTO_INCREMENT,
	source VARCHAR(40) COLLATE utf8mb4_bin NOT NULL,
	adjustment VARCHAR(20) COLLATE utf8mb4_bin NOT NULL,
	archive_sha256 VARCHAR(64) COLLATE utf8mb4_bin,
	archive_key VARBINARY(256)
    GENERATED ALWAYS AS (CAST(IFNULL(archive_sha256, '') AS BINARY)) STORED,
	archive_is_null INTEGER UNSIGNED GENERATED ALWAYS AS (archive_sha256 IS NULL) STORED,
	source_key VARBINARY(160) GENERATED ALWAYS AS (CAST(source AS BINARY)) STORED,
	adjustment_key VARBINARY(80) GENERATED ALWAYS AS (CAST(adjustment AS BINARY)) STORED,
	CONSTRAINT pk_bar_provenance PRIMARY KEY (id),
	CONSTRAINT uq_bar_provenance UNIQUE (source_key, adjustment_key, archive_key, archive_is_null)
)CHARSET=utf8mb4 ENGINE=InnoDB"""
_BAR_COLUMNS = {
    "symbol",
    "trading_day",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "available_at",
}
_PROVENANCE_COLUMNS = {
    "id",
    "source",
    "adjustment",
    "archive_sha256",
    "archive_key",
    "archive_is_null",
    "source_key",
    "adjustment_key",
}


def upgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("此历史 revision 需要在线检查结构，不支持离线生成升级 SQL")
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    names = {c["name"] for c in inspector.get_columns("daily_bars")}
    if "provenance_id" in names:
        if names != _BAR_COLUMNS | {"provenance_id"}:
            raise RuntimeError("日线结构混合，拒绝升级")
        if not inspector.has_table("bar_provenance"):
            raise RuntimeError("共享来源表缺失，需完成冷迁移")
        if {c["name"] for c in inspector.get_columns("bar_provenance")} != _PROVENANCE_COLUMNS:
            raise RuntimeError("共享来源结构不完整，需完成冷迁移")
        return  # 已具备本 revision 的结构，只推进版本标记。
    if names != _BAR_COLUMNS | {"source", "adjustment", "archive_sha256"}:
        raise RuntimeError("日线旧结构不完整，需先完成此前迁移")
    if bind.scalar(sa.text("SELECT symbol FROM daily_bars LIMIT 1")) is not None:
        raise RuntimeError("不再支持有数据的旧日线结构；请恢复当前结构的备份或初始化空库")
    op.execute(sa.text(_PROVENANCE_SQL))
    op.execute(
        sa.text(
            "ALTER TABLE daily_bars ADD COLUMN provenance_id INT UNSIGNED NOT NULL, "
            "DROP COLUMN source, DROP COLUMN adjustment, DROP COLUMN archive_sha256"
        )
    )


def downgrade() -> None:
    raise RuntimeError("不支持自动恢复旧日线格式；请使用数据库备份恢复")
