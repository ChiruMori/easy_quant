import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def migration():
    path = Path(__file__).parents[2] / "migrations/versions/0011_compact_daily_bars.py"
    spec = importlib.util.spec_from_file_location("cold_bar_schema", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("mode", ["empty", "populated", "compact", "missing-provenance", "mixed"])
def test_cold_schema_upgrade_does_not_automatically_rebuild_populated_bars(monkeypatch, mode):
    module = migration()
    actions = []
    bind = SimpleNamespace(scalar=lambda _query: "000001" if mode == "populated" else None)
    names = module._BAR_COLUMNS | {"source", "adjustment", "archive_sha256"}
    if mode in {"compact", "missing-provenance"}:
        names = module._BAR_COLUMNS | {"provenance_id"}
    if mode == "mixed":
        names.add("provenance_id")
    monkeypatch.setattr(module.op, "get_context", lambda: SimpleNamespace(as_sql=False))
    monkeypatch.setattr(module.op, "get_bind", lambda: bind)
    monkeypatch.setattr(
        module.sa,
        "inspect",
        lambda _bind: SimpleNamespace(
            get_columns=lambda table: [
                {"name": n}
                for n in (names if table == "daily_bars" else module._PROVENANCE_COLUMNS)
            ],
            has_table=lambda _table: mode != "missing-provenance",
        ),
    )
    monkeypatch.setattr(module.op, "execute", lambda query: actions.append(str(query)))
    if mode in {"populated", "missing-provenance", "mixed"}:
        with pytest.raises(RuntimeError):
            module.upgrade()
        assert actions == []
    else:
        module.upgrade()
        if mode == "empty":
            assert actions[0].startswith("CREATE TABLE IF NOT EXISTS bar_provenance")
            assert "FOREIGN KEY" not in actions[0]
            assert len(actions) == 2 and actions[1].startswith("ALTER TABLE daily_bars")
            assert "provenance_id INT UNSIGNED" in actions[1]
            assert "FOREIGN KEY" not in actions[1]
        else:
            assert actions == []


def test_offline_upgrade_and_automatic_downgrade_require_explicit_cold_workflow(monkeypatch):
    module = migration()
    monkeypatch.setattr(module.op, "get_context", lambda: SimpleNamespace(as_sql=True))
    with pytest.raises(RuntimeError, match="在线检查结构"):
        module.upgrade()
    with pytest.raises(RuntimeError, match="数据库备份"):
        module.downgrade()
