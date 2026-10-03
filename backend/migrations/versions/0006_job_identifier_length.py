"""容纳带业务前缀的后台任务标识。"""

import sqlalchemy as sa
from alembic import op

revision = "0006_job_identifier_length"
down_revision = "0005_large_run_payloads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "jobs", "id", existing_type=sa.String(36), type_=sa.String(64), existing_nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "jobs", "id", existing_type=sa.String(64), type_=sa.String(36), existing_nullable=False
    )
