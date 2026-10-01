import pytest

from easy_quant.domain.shared.errors import NotFoundError
from easy_quant.factors.registry import build_default_registry


def test_registry_has_complete_read_only_documents() -> None:
    factors = build_default_registry().list()
    assert len(factors) >= 4
    assert all(item.description and item.example and item.output for item in factors)


def test_unknown_factor_is_explicit() -> None:
    with pytest.raises(NotFoundError):
        build_default_registry().get("unknown")
