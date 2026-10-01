from dataclasses import dataclass

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
