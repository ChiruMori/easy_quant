from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from sqlalchemy.orm import Session

from easy_quant.domain.market_data.entities import RawEnvelope
from easy_quant.infrastructure.persistence.repositories.raw_cache import (
    SqlAlchemyCompressedRawCache,
)


def test_cache_write_failure_rolls_back_session(fixed_now) -> None:
    class FailedSession:
        rolled_back = False

        def merge(self, _row):
            return None

        def commit(self):
            raise RuntimeError("cache write failed")

        def rollback(self):
            self.rolled_back = True

    session = FailedSession()
    cache = SqlAlchemyCompressedRawCache(cast(Session, session))
    envelope = RawEnvelope(
        "identity",
        "source",
        b"payload",
        "application/json",
        fixed_now,
        fixed_now + timedelta(hours=1),
    )
    with pytest.raises(RuntimeError, match="cache write failed"):
        cache.put(envelope)
    assert session.rolled_back
