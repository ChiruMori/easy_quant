import hashlib
import json
from datetime import timedelta

import httpx
import pytest

from easy_quant.application.services.acquisition import (
    AcquisitionFailed,
    AcquisitionService,
    ExponentialRetry,
)
from easy_quant.application.services.market_data_sync import (
    MarketDataSyncService,
    validate_daily_response,
)
from easy_quant.domain.market_data.entities import RawEnvelope, SemanticRequest
from easy_quant.domain.market_data.indices import INDEX_CATALOG
from easy_quant.infrastructure.data_sources.akshare.daily import AkShareDailySource
from easy_quant.infrastructure.data_sources.tencent.adapters import TencentDailySource
from tests.application.test_acquisition_service import MemoryCache, Source
from tests.fakes.core import FixedClock, VirtualSleeper
from tests.fakes.platform import make_test_container


def request(symbol="sh000001"):
    return SemanticRequest(
        "daily-bars",
        {
            "symbol": symbol,
            "start_date": "2026-10-01",
            "end_date": "2026-10-15",
            "required_end_date": "2026-10-15",
        },
        "index-v1",
    )


def valid_rows():
    return [
        {
            "date": "2026-10-15",
            "open": "100",
            "high": "102",
            "low": "99",
            "close": "101",
            "volume": "200",
        }
    ]


@pytest.mark.parametrize("symbol", list(INDEX_CATALOG))
def test_tencent_indices_bypass_stock_listing_probe_and_accept_variable_fields(symbol):
    seen = []

    def reply(http_request):
        seen.append(http_request)
        assert http_request.url.params["param"].endswith(",640,")
        data = {
            "code": 0,
            "data": {
                symbol: {
                    "day": [
                        ["2026-09-30", "1", "1", "1", "1", "1"],
                        ["2026-10-15", "100", "101", "102", "99", "200", "extra"],
                    ]
                }
            },
        }
        return httpx.Response(200, text="kline_day=" + json.dumps(data))

    source = TencentDailySource(httpx.Client(transport=httpx.MockTransport(reply)), None)
    payload, _ = source.fetch(request(symbol))
    validate_daily_response(request(symbol), payload)
    assert len(json.loads(payload)) == 1 and len(seen) == 1


@pytest.mark.parametrize("symbol", list(INDEX_CATALOG))
def test_sina_indices_use_bounded_client_and_fixed_decoder(symbol):
    def reply(http_request):
        assert symbol in http_request.url.path
        return httpx.Response(200, text='var history="encoded";')

    def decode(encoded):
        assert encoded == "encoded"
        return valid_rows()

    source = AkShareDailySource(httpx.Client(transport=httpx.MockTransport(reply)), None, decode)
    payload, _ = source.fetch(request(symbol))
    validate_daily_response(request(symbol), payload)


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {"data": None},
        {"data": {"klines": []}},
        [{"date": "2026-10-15", "close": "NaN"}],
        [{**valid_rows()[0], "close": "NaN"}],
        [{**valid_rows()[0], "date": "2026-09-30"}],
        [{**valid_rows()[0], "date": "2026-10-14"}],
    ],
)
def test_empty_malformed_or_stale_data_falls_back_instead_of_success(bad, fixed_now):
    first = Source("eastmoney", payload=json.dumps(bad).encode())
    second = Source("tencent", payload=json.dumps(valid_rows()).encode())
    service = AcquisitionService(
        [first, second],
        MemoryCache(),
        FixedClock(fixed_now),
        VirtualSleeper(),
        ExponentialRetry(max_attempts=1),
        shuffle=lambda _: None,
        validate=validate_daily_response,
    )
    envelope, attempts = service.acquire_with_attempts(request())
    assert envelope.source_key == "tencent"
    assert [item.status.value for item in attempts] == ["failed", "succeeded"]


def test_invalid_legacy_cache_is_never_returned(fixed_now):
    identity = hashlib.sha256(b"eastmoney:index-v1").hexdigest()
    cache = MemoryCache(
        RawEnvelope(
            identity,
            "eastmoney",
            b'{"data":null}',
            "application/json",
            fixed_now,
            fixed_now + timedelta(hours=1),
        )
    )
    source = Source("eastmoney", payload=json.dumps(valid_rows()).encode())
    service = AcquisitionService(
        [source],
        cache,
        FixedClock(fixed_now),
        VirtualSleeper(),
        shuffle=lambda _: None,
        validate=validate_daily_response,
    )
    envelope, attempts = service.acquire_with_attempts(request())
    assert source.calls == 1 and json.loads(envelope.payload)
    assert attempts[0].status.value == "failed" and attempts[-1].status.value == "succeeded"


def test_partial_index_batch_retains_successes_and_reports_failed_symbols():
    from tests.application.test_market_data_sync import FakeAcquisition

    class Feed(FakeAcquisition):
        def acquire_with_attempts(self, request, **kwargs):
            if request.parameters["symbol"] == "sh000016":
                raise AcquisitionFailed(
                    "无有效行情",
                    {
                        "attempts": [
                            {
                                "source_key": "eastmoney",
                                "attempt": 1,
                                "status": "failed",
                                "message": "空日线",
                            }
                        ]
                    },
                )
            return super().acquire_with_attempts(request, **kwargs)

    container = make_test_container()
    service = MarketDataSyncService({"daily-bars": Feed(valid_rows())}, container.market_data)
    from datetime import date

    with pytest.raises(AcquisitionFailed) as error:
        service.sync(
            "daily-bars",
            symbols=["sh000001", "sh000016"],
            start_day=date(2026, 10, 1),
            end_day=date(2026, 10, 15),
        )
    assert error.value.details["record_count"] == 1
    assert "sh000016" in str(error.value.details["failed_symbols"])
    assert len(container.market_data.list_bars(symbol="sh000001")) == 1
    assert container.market_data.list_bars(symbol="sh000016") == []
