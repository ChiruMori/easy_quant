import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def test_index_migration_inserts_disabled_plan_without_overwriting_existing(monkeypatch):
    path = Path(__file__).parents[2] / "migrations/versions/0014_index_daily_schedule.py"
    spec = importlib.util.spec_from_file_location("index_schedule_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    class Connection:
        def execute(self, statement, parameters):
            calls.append((str(statement), parameters))

    monkeypatch.setattr(module, "op", SimpleNamespace(get_bind=lambda: Connection()))
    module.upgrade()
    sql, parameters = calls[0]
    payload = json.loads(parameters["payload"])
    assert payload["enabled"] is False
    assert payload["task_type"] == "index-daily-update"
    assert payload["id"] == parameters["key"]
    assert payload["schedule_expression"] == "0 22 * * 1-5"
    assert payload["timezone"] == "Asia/Shanghai"
    assert "WHERE NOT EXISTS" in sql and "$.task_type" in sql and "`key` = :key" in sql
    assert "UPDATE" not in sql and "DELETE" not in sql
    module.downgrade()
    assert len(calls) == 1
