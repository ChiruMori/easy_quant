from dataclasses import dataclass
from typing import cast

import pytest

from easy_quant.application.services.acquisition import (
    AcquisitionFailed,
    AcquisitionService,
    ExponentialRetry,
)
from easy_quant.domain.market_data.entities import RawEnvelope, SemanticRequest
from tests.fakes.core import FixedClock, VirtualSleeper


@dataclass
class MemoryCache:
    value: RawEnvelope | None = None

    def get(self, request_identity: str):
        return (
            self.value if self.value and self.value.request_identity == request_identity else None
        )

    def put(self, envelope: RawEnvelope):
        self.value = envelope


@dataclass
class Source:
    key: str
    failures: int = 0
    calls: int = 0
    payload: bytes = b"[]"

    def fetch(self, request):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("temporary")
        return self.payload, "application/json"


def test_retry_then_stop_at_first_success(fixed_now) -> None:
    first, second = Source("a", failures=3), Source("b")
    sleeper = VirtualSleeper()
    service = AcquisitionService(
        [first, second],
        MemoryCache(),
        FixedClock(fixed_now),
        sleeper,
        ExponentialRetry(3, 1),
        shuffle=lambda sources: None,
    )
    result = service.acquire(SemanticRequest("bars", {}, "identity"))
    assert result.source_key == "b"
    assert (first.calls, second.calls) == (3, 1)
    assert sleeper.calls == [1, 2]


def test_all_sources_failed(fixed_now) -> None:
    service = AcquisitionService(
        [Source("a", failures=3)],
        MemoryCache(),
        FixedClock(fixed_now),
        VirtualSleeper(),
        shuffle=lambda sources: None,
    )
    with pytest.raises(AcquisitionFailed):
        service.acquire(SemanticRequest("bars", {}, "identity"))


def test_source_failure_redacts_query_tokens_but_keeps_reason(fixed_now) -> None:
    class FailingSource(Source):
        def fetch(self, request):
            raise RuntimeError(
                "ProxyError https://fixture-user:fixture-pass@example.invalid/kline/get"
                "?ut=sample-token&beg=20260903 disconnected Authorization: Basic fixture-auth"
            )

    service = AcquisitionService(
        [FailingSource("eastmoney")],
        MemoryCache(),
        FixedClock(fixed_now),
        VirtualSleeper(),
        ExponentialRetry(1),
    )
    with pytest.raises(AcquisitionFailed) as captured:
        service.acquire(SemanticRequest("bars", {}, "identity"))
    message = str(captured.value.details["attempts"])
    assert "ProxyError" in message
    assert "sample-token" not in message
    assert all(secret not in message for secret in ["fixture-user", "fixture-pass", "fixture-auth"])


def test_randomized_source_order_is_used(fixed_now) -> None:
    first, second = Source("a"), Source("b")

    def reverse(sources) -> None:
        sources.reverse()

    service = AcquisitionService(
        [first, second],
        MemoryCache(),
        FixedClock(fixed_now),
        VirtualSleeper(),
        shuffle=reverse,
    )
    result = service.acquire(SemanticRequest("bars", {}, "identity"))
    assert result.source_key == "b"
    assert (first.calls, second.calls) == (0, 1)


def test_cache_write_failure_does_not_refetch_or_try_another_source(fixed_now) -> None:
    class FailingCache(MemoryCache):
        def put(self, envelope: RawEnvelope):
            raise RuntimeError("cache write failed")

    first, second = Source("a"), Source("b")
    service = AcquisitionService(
        [first, second],
        FailingCache(),
        FixedClock(fixed_now),
        VirtualSleeper(),
        shuffle=lambda sources: None,
    )
    with pytest.raises(RuntimeError, match="cache write failed"):
        service.acquire(SemanticRequest("securities", {}, "identity"))
    assert (first.calls, second.calls) == (1, 0)


def test_round_retries_visit_every_source_before_retrying_and_log_reasons(fixed_now, caplog):
    calls = []

    class FailingSource(Source):
        def fetch(self, request):
            calls.append(self.key)
            raise RuntimeError('HTTP 403 password="two word fixture" token=hidden-token')

    sleeper = VirtualSleeper()
    service = AcquisitionService(
        [FailingSource("a"), FailingSource("b")],
        MemoryCache(),
        FixedClock(fixed_now),
        sleeper,
        ExponentialRetry(2, 0.25),
        shuffle=lambda _: None,
        retry_by_round=True,
    )
    with caplog.at_level("INFO"), pytest.raises(AcquisitionFailed) as captured:
        service.acquire(SemanticRequest("live-quotes", {}, "q"), force=True)
    assert calls == ["a", "b", "a", "b"]
    assert sleeper.calls == [0.25]
    assert len(cast(list, captured.value.details["attempts"])) == 4
    assert "dataset=live-quotes source=a attempt=2" in caplog.text
    assert "RuntimeError: HTTP 403" in caplog.text
    assert "two word fixture" not in caplog.text and "hidden-token" not in caplog.text
    assert "two word fixture" not in str(captured.value.details)


def test_invalid_quotes_switch_source_before_success_is_recorded(fixed_now):
    from easy_quant.application.services.market_data_sync import validate_live_quote_response

    first = Source("a", payload=b'{"data": null}')
    second = Source("b", payload=b'[{"code":"000001","price":"10"}]')
    service = AcquisitionService(
        [first, second],
        MemoryCache(),
        FixedClock(fixed_now),
        VirtualSleeper(),
        ExponentialRetry(2),
        shuffle=lambda _: None,
        retry_by_round=True,
        validate=validate_live_quote_response,
    )
    value, attempts = service.acquire_with_attempts(
        SemanticRequest("live-quotes", {"symbols": ["000001"]}, "q"), force=True
    )
    assert value.source_key == "b" and (first.calls, second.calls) == (1, 1)
    assert attempts[0].message is not None and "实时价格缺失" in attempts[0].message


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity", None, "bad"])
def test_invalid_quote_price_never_counts_as_source_success(price):
    import json

    from easy_quant.application.services.market_data_sync import validate_live_quote_response

    with pytest.raises(ValueError):
        validate_live_quote_response(
            SemanticRequest("live-quotes", {"symbols": ["000001"]}, "q"),
            json.dumps([{"code": "000001", "price": price}]).encode(),
        )
