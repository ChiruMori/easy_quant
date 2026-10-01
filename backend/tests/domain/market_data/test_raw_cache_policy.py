from datetime import timedelta

from easy_quant.domain.market_data.entities import RawEnvelope
from easy_quant.domain.market_data.request_identity import semantic_request_identity


def test_semantic_identity_ignores_transient_fields() -> None:
    first = semantic_request_identity("daily-bars", {"symbol": "000001", "timestamp": 1})
    second = semantic_request_identity("daily-bars", {"timestamp": 2, "symbol": "000001"})
    assert first == second


def test_cache_freshness_and_corruption(fixed_now) -> None:
    envelope = RawEnvelope(
        "key", "source", b"raw", "application/json", fixed_now, fixed_now + timedelta(minutes=1)
    )
    assert envelope.is_fresh(fixed_now)
    assert envelope.is_valid()
    envelope.payload = b"broken"
    assert not envelope.is_valid()
