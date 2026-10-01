from __future__ import annotations

from easy_quant.application.ports.core import IdGenerator
from easy_quant.domain.backtesting.snapshots import DataSnapshot, canonical_snapshot_bytes


class SnapshotService:
    def __init__(self, ids: IdGenerator) -> None:
        self.ids = ids
        self.by_digest: dict[str, DataSnapshot] = {}

    def get_or_create(self, records: list[dict[str, object]]) -> DataSnapshot:
        import hashlib

        digest = hashlib.sha256(canonical_snapshot_bytes(records)).hexdigest()
        existing = self.by_digest.get(digest)
        if existing is not None:
            return existing
        snapshot = DataSnapshot.build(self.ids.new(), records)
        self.by_digest[digest] = snapshot
        return snapshot
