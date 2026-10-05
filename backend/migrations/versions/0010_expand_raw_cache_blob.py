"""扩大原始响应缓存容量，容纳完整证券清单。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGBLOB

revision = "0010_expand_raw_cache_blob"
down_revision = "0009_repair_runtime_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "raw_cache",
        "payload_gzip",
        existing_type=sa.LargeBinary(),
        type_=LONGBLOB(),
        existing_nullable=False,
    )


def downgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("缩小原始响应缓存字段需要在线检查已有内容")
    maximum = op.get_bind().scalar(sa.text("SELECT MAX(OCTET_LENGTH(payload_gzip)) FROM raw_cache"))
    if maximum is not None and maximum > 65535:
        raise RuntimeError("原始响应缓存含超过 BLOB 上限的记录，不能安全回退")
    op.alter_column(
        "raw_cache",
        "payload_gzip",
        existing_type=LONGBLOB(),
        type_=sa.LargeBinary(),
        existing_nullable=False,
    )
