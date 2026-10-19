"""预置默认停用的主要指数同步计划，不覆盖管理员已有计划。"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0014_index_daily_schedule"
down_revision = "0013_strategy_workspace"
branch_labels = None
depends_on = None


def upgrade():
    payload = {
        "id": "schedule-index-daily-update",
        "task_type": "index-daily-update",
        "schedule_kind": "cron",
        "schedule_expression": "0 22 * * 1-5",
        "timezone": "Asia/Shanghai",
        "configuration": {},
        "enabled": False,
        "next_run_at": "1970-01-01T00:00:00+00:00",
    }
    op.get_bind().execute(
        sa.text("""INSERT INTO runtime_documents (namespace, `key`, payload_json)
            SELECT 'schedules', :key, :payload WHERE NOT EXISTS (
                SELECT 1 FROM runtime_documents WHERE namespace = 'schedules'
                AND (`key` = :key OR
                    JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.task_type')) = 'index-daily-update')
            )"""),
        {"key": payload["id"], "payload": json.dumps(payload, ensure_ascii=False)},
    )


def downgrade():
    # 保留管理员可能已编辑、启用的计划及其执行历史。
    pass
