from easy_quant.application.services.data_snapshots import SnapshotService
from tests.fakes.core import SequentialIdGenerator


def test_snapshot_reuse_and_current_data_changes_do_not_mutate_snapshot() -> None:
    service = SnapshotService(SequentialIdGenerator())
    records: list[dict[str, object]] = [
        {"symbol": "000001", "close": "10", "available_at": "2026-01-01"}
    ]
    first = service.get_or_create(records)
    for _ in range(10):
        assert service.get_or_create(list(records)).id == first.id
    records[0]["close"] = "11"
    assert b'"close":"10"' in first.payload()
