import gzip
import hashlib
import json

import pytest

from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.infrastructure.persistence.snapshot_prices import snapshot_prices


def test_reads_split_compressed_unicode_snapshot_without_later_quotes():
    rows = [
        {"symbol": "000001", "name": "平安银行", "trading_day": day, "close": str(price)}
        for day, price in (("2026-10-20", 10), ("2026-10-21", 11), ("2026-10-22", 999))
    ]
    raw = json.dumps(rows, ensure_ascii=False).encode()
    compressed = gzip.compress(raw)
    result = snapshot_prices(
        (compressed[i : i + 1] for i in range(len(compressed))),
        hashlib.sha256(raw).hexdigest(),
        "2026-10-21",
        {"000001"},
    )
    assert result == {"000001": 11}
    assert snapshot_prices([], "missing", "2026-10-21", {"000001"}) == {}
    with pytest.raises(StateConflictError):
        snapshot_prices([compressed], "bad-digest", "2026-10-21", {"000001"})
    with pytest.raises(StateConflictError):
        snapshot_prices(
            [compressed[:-4]], hashlib.sha256(raw).hexdigest(), "2026-10-21", {"000001"}
        )
