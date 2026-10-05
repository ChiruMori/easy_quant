from typing import Any, cast

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


def test_existing_daily_dataset_gets_independent_source_once() -> None:
    datasets = [
        {
            "key": "daily-bars",
            "sources": [{"key": "eastmoney", "name": "东方财富", "enabled": False}],
        }
    ]
    bootstrap._ensure_independent_daily_source(datasets)
    bootstrap._ensure_independent_daily_source(datasets)
    assert datasets[0]["sources"] == [
        {"key": "eastmoney", "name": "东方财富", "enabled": False},
        {"key": "tencent", "name": "腾讯行情", "enabled": True},
    ]


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


def test_security_catalog_includes_both_shanghai_boards(monkeypatch) -> None:
    import akshare as ak
    import pandas as pd

    from tests.fakes.platform import make_test_container

    seen: list[str] = []

    def sh_board(*, symbol: str):
        seen.append(symbol)
        code = "600001" if symbol == "主板A股" else "688001"
        return pd.DataFrame([{"证券代码": code, "证券简称": symbol}])

    monkeypatch.setattr(ak, "stock_info_sh_name_code", sh_board)
    monkeypatch.setattr(
        ak,
        "stock_info_sz_name_code",
        lambda: pd.DataFrame([{"A股代码": "000001", "A股简称": "深市"}]),
    )
    monkeypatch.setattr(
        ak,
        "stock_info_bj_name_code",
        lambda: pd.DataFrame([{"证券代码": "830001", "证券简称": "北交所"}]),
    )
    container = make_test_container()
    service = bootstrap._build_market_data_sync(container, object())
    source = cast(Any, service.acquisitions["securities"]).sources[0]
    rows = source.functions["securities"]()

    assert seen == ["主板A股", "科创板"]
    assert set(rows["code"]) == {"600001", "688001", "000001", "830001"}


def test_akshare_daily_bars_use_requested_adjustment(monkeypatch) -> None:
    import akshare as ak
    import pandas as pd

    from tests.fakes.platform import make_test_container

    seen: list[str] = []

    def bars(**parameters):
        seen.append(parameters["adjust"])
        return pd.DataFrame()

    monkeypatch.setattr(ak, "stock_zh_a_hist", bars)
    service = bootstrap._build_market_data_sync(make_test_container(), object())
    source = cast(Any, service.acquisitions["daily-bars"]).sources[0]
    for adjustment in ("none", "qfq"):
        source.functions["daily-bars"](
            symbol="000016", start_date="2026-09-03", end_date="2026-09-30", adjustment=adjustment
        )
    assert seen == ["", "qfq"]


def test_tencent_daily_bars_use_market_prefix_and_adjustment(monkeypatch) -> None:
    import akshare as ak
    import pandas as pd

    from tests.fakes.platform import make_test_container

    seen: list[dict[str, object]] = []

    def bars(**parameters):
        seen.append(parameters)
        return pd.DataFrame()

    monkeypatch.setattr(ak, "stock_zh_a_hist_tx", bars)
    service = bootstrap._build_market_data_sync(make_test_container(), object())
    source = next(
        source
        for source in cast(Any, service.acquisitions["daily-bars"]).sources
        if source.key == "tencent"
    )
    for symbol, adjustment in (("000016", "none"), ("600000", "qfq"), ("830001", "none")):
        source.functions["daily-bars"](
            symbol=symbol,
            start_date="2026-09-03",
            end_date="2026-09-30",
            adjustment=adjustment,
        )
    assert [(item["symbol"], item["adjust"]) for item in seen] == [
        ("sz000016", ""),
        ("sh600000", "qfq"),
        ("bj830001", ""),
    ]
