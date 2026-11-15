"""仅解析本地迁移图，不加载env.py、不访问数据库。"""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory


def migration_scripts():
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    return ScriptDirectory.from_config(config)


def test_upgrade_head_resolves_to_one_revision():
    scripts = migration_scripts()
    head = scripts.get_current_head()  # 与upgrade head相同的唯一head要求。
    assert head is not None
    assert "8fdd8d82f252" in {
        revision.revision for revision in scripts.walk_revisions(base="base", head=head)
    }


@pytest.mark.parametrize(
    ("current", "pending"),
    [
        (
            "0014_index_daily_schedule",
            {"0015_backtest_name", "0015_financial_records", "8fdd8d82f252"},
        ),
        ("0015_backtest_name", {"0015_financial_records", "8fdd8d82f252"}),
        ("0015_financial_records", {"0015_backtest_name", "8fdd8d82f252"}),
        (("0015_backtest_name", "0015_financial_records"), {"8fdd8d82f252"}),
        ("8fdd8d82f252", set()),
    ],
)
def test_merge_upgrade_plan_preserves_applied_branches(current, pending):
    # Alembic的实际升级规划器；不执行任何迁移函数。
    steps = migration_scripts()._upgrade_revs("8fdd8d82f252", current)
    assert {step.revision.revision for step in steps} == pending
    if steps:
        assert steps[-1].revision.revision == "8fdd8d82f252"
