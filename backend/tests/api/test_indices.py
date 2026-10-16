from datetime import date

import pytest

from easy_quant.application.services.market_data_sync import MarketDataSyncService
from easy_quant.domain.identity.entities import UserRole
from easy_quant.worker.handlers.market_data import register_market_data_handlers
from easy_quant.worker.registry import JobHandlerRegistry
from tests.api.test_strategy_library import authenticated
from tests.application.test_market_data_sync import FakeAcquisition
from tests.fakes.platform import make_test_container


def setup():
    container = make_test_container(initialize_admin=True)
    client, headers = authenticated(container)
    return container, client, headers


def test_index_catalog_works_before_stock_refresh_without_writing():
    container, client, _ = setup()
    result = client.get("/api/v1/admin/market-data/indices")
    assert result.status_code == 200
    data = result.get_json()["data"]
    assert len(data["items"]) == 7
    csi = next(row for row in data["items"] if row["symbol"] == "sh000300")
    assert csi["name"] == "沪深300" and csi["record_count"] == 0
    assert not csi["tradable"] and csi["sync_status"] == "未同步"
    assert container.market_data.list_instruments() == []
    assert not container.state.acquisitions


def test_stock_tab_coverage_excludes_index_symbols_and_counts():
    container, client, _ = setup()
    container.market_data.upsert_instruments(
        [
            {"symbol": "000001", "name": "平安银行"},
            {"symbol": "sh000001", "name": "上证指数"},
            {"symbol": "sz399001", "name": "深证成指"},
        ]
    )
    data = client.get("/api/v1/admin/market-data/coverage?instrument_type=stock").get_json()["data"]
    assert data["total"] == data["instrument_count"] == 1
    assert [item["symbol"] for item in data["items"]] == ["000001"]


@pytest.mark.parametrize(
    "change",
    [
        {"symbols": []},
        {"symbols": ["000001"]},
        {"symbols": ["sh000300", "600000"]},
        {"start_day": "2026-09-30"},
        {"end_day": "bad"},
    ],
)
def test_invalid_index_sync_cannot_enqueue(change):
    container, client, headers = setup()
    payload = {"symbols": ["sh000300"], "start_day": "2026-09-28", "end_day": "2026-09-29"}
    result = client.post(
        "/api/v1/admin/market-data/indices/acquisitions",
        json={**payload, **change},
        headers=headers,
    )
    assert result.status_code == 422
    assert all(
        "input" not in issue and "ctx" not in issue
        for issue in result.get_json()["error"]["details"]["issues"]
    )
    assert not container.state.acquisitions


def test_index_api_requires_admin():
    container, client, headers = setup()
    owner = container.authentication.repository.get_user_by_username("admin")
    assert owner
    owner.role = UserRole.USER
    container.authentication.repository.save_user(owner)
    assert client.get("/api/v1/admin/market-data/indices").status_code == 403
    assert (
        client.post(
            "/api/v1/admin/market-data/indices/acquisitions", headers=headers, json={}
        ).status_code
        == 403
    )


def test_index_sync_worker_updates_coverage_and_retries_without_duplicates():
    container, client, headers = setup()
    feed = FakeAcquisition(
        [
            {
                "日期": "2026-09-28",
                "开盘": "100",
                "收盘": "101",
                "最高": "102",
                "最低": "99",
                "成交量": "200",
            }
        ]
    )
    container.data_sync = MarketDataSyncService({"daily-bars": feed}, container.market_data)
    registry = JobHandlerRegistry()
    register_market_data_handlers(registry, container)
    body = {"symbols": ["000300", "SH000300"], "start_day": "2026-09-28", "end_day": "2026-09-28"}
    for _ in range(2):
        result = client.post(
            "/api/v1/admin/market-data/indices/acquisitions", headers=headers, json=body
        )
        assert result.status_code == 202
        task = result.get_json()["data"]
        assert task["symbols"] == ["sh000300"] and task["dataset_key"] == "daily-bars"
        job = container.jobs.get(task["job_id"])
        assert job is not None
        registry.get(job.job_type)(job)
        status = client.get(f"/api/v1/admin/market-data/acquisitions/{task['id']}").get_json()[
            "data"
        ]
        assert status["status"] == "succeeded"
    assert feed.requests[0].parameters["adjustment"] == "none"
    assert feed.source_keys[0] == {"akshare", "eastmoney", "tencent"}
    rows = client.get("/api/v1/admin/market-data/indices").get_json()["data"]["items"]
    item = next(row for row in rows if row["symbol"] == "sh000300")
    assert item["record_count"] == 1
    assert item["first_trading_day"] == item["last_trading_day"] == "2026-09-28"
    assert container.market_data.list_bars(date(2026, 9, 28), date(2026, 9, 28), "sh000300")


def test_failed_index_source_keeps_coverage_empty_and_can_be_retried():
    from easy_quant.application.services.acquisition import AcquisitionFailed

    class FailedFeed(FakeAcquisition):
        def acquire_with_attempts(self, request, *, force=False, source_keys=None):
            raise AcquisitionFailed(
                "离线来源暂不可用",
                {
                    "attempts": [
                        {
                            "source_key": "akshare",
                            "attempt": 1,
                            "status": "failed",
                            "message": "离线失败",
                        }
                    ]
                },
            )

    container, client, headers = setup()
    container.data_sync = MarketDataSyncService(
        {"daily-bars": FailedFeed([])}, container.market_data
    )
    registry = JobHandlerRegistry()
    register_market_data_handlers(registry, container)
    body = {"symbols": ["sh000300"], "start_day": "2026-09-28", "end_day": "2026-09-28"}
    task = client.post(
        "/api/v1/admin/market-data/indices/acquisitions", headers=headers, json=body
    ).get_json()["data"]
    job = container.jobs.get(task["job_id"])
    assert job
    with pytest.raises(AcquisitionFailed):
        registry.get(job.job_type)(job)
    failed = client.get(f"/api/v1/admin/market-data/acquisitions/{task['id']}").get_json()["data"]
    assert failed["status"] == "failed" and failed["attempts"][0]["status"] == "failed"
    assert not container.market_data.list_bars(symbol="sh000300")
    container.data_sync.acquisitions["daily-bars"] = FakeAcquisition(
        [
            {
                "date": "2026-09-28",
                "open": "100",
                "high": "100",
                "low": "100",
                "close": "100",
                "volume": "200",
            }
        ]
    )
    retry = client.post(
        "/api/v1/admin/market-data/indices/acquisitions", headers=headers, json=body
    ).get_json()["data"]
    retry_job = container.jobs.get(retry["job_id"])
    assert retry_job
    registry.get(retry_job.job_type)(retry_job)
    assert len(container.market_data.list_bars(symbol="sh000300")) == 1
