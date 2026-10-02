from pydantic import SecretStr, ValidationError

from easy_quant import __version__, bootstrap
from easy_quant.config import Settings


def test_package_imports() -> None:
    assert __version__ == "0.1.0"


def test_legacy_dataset_label_is_updated_without_changing_source_configuration() -> None:
    sources = [{"key": "eastmoney", "enabled": False}]
    datasets = [
        {"key": "daily-bars", "description": "前复权日线开高低收与成交量", "sources": sources},
        {"key": "daily-bars", "description": "自定义说明", "sources": sources},
    ]
    bootstrap._refresh_dataset_description(datasets)
    assert "不复权" in datasets[0]["description"]
    assert datasets[0]["sources"] == sources
    assert datasets[1]["description"] == "自定义说明"


def test_database_url_is_required(monkeypatch) -> None:
    monkeypatch.delenv("EASY_QUANT_DATABASE_URL", raising=False)
    try:
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    except ValidationError:
        return
    raise AssertionError("缺少数据库 URL 时必须拒绝启动配置")


def test_runtime_container_always_uses_configured_database(monkeypatch) -> None:
    class ScopedSession:
        remove_calls = 0

        def remove(self) -> None:
            self.remove_calls += 1

    session = ScopedSession()
    seen_urls: list[str] = []

    class Identity:
        def has_any_user(self) -> bool:
            return True

    monkeypatch.setattr(
        bootstrap,
        "create_database_engine",
        lambda url: seen_urls.append(url) or "engine",
    )
    monkeypatch.setattr(bootstrap, "create_session_factory", lambda _engine: lambda: session)
    monkeypatch.setattr(bootstrap, "create_scoped_session", lambda _factory: session)
    monkeypatch.setattr(bootstrap, "SqlAlchemyIdentityRepository", lambda _session: Identity())
    monkeypatch.setattr(bootstrap, "SqlAlchemyStrategyRepository", lambda _session: object())
    monkeypatch.setattr(bootstrap, "SqlAlchemyMarketDataStore", lambda _session: object())
    monkeypatch.setattr(bootstrap, "SqlAlchemyBacktestStore", lambda _session: object())
    monkeypatch.setattr(bootstrap, "SqlAlchemyJobRepository", lambda _session: object())
    monkeypatch.setattr(bootstrap, "SqlAlchemyCompressedRawCache", lambda _session: object())
    monkeypatch.setattr(bootstrap, "SqlJsonList", lambda _session, _namespace: [])
    monkeypatch.setattr(bootstrap, "SqlJsonDict", lambda _session, _namespace: {})
    monkeypatch.setattr(bootstrap, "_build_market_data_sync", lambda _container, _cache: object())

    settings = Settings(
        database_url=SecretStr("mysql+pymysql://configured/db"),
        secret_key=SecretStr("test-secret"),
    )
    container = bootstrap.build_container(settings)

    assert seen_urls == ["mysql+pymysql://configured/db"]
    assert container.database_session is session
    assert session.remove_calls == 1
