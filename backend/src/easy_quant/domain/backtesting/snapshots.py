from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, Decimal)):
        return str(value)
    raise TypeError(f"无法序列化 {type(value).__name__}")


def canonical_snapshot_bytes(records: list[dict[str, object]]) -> bytes:
    return json.dumps(
        records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode()


@dataclass(frozen=True, slots=True)
class DataSnapshot:
    id: str
    content_sha256: str
    record_count: int
    compressed_chunks: tuple[bytes, ...]

    @classmethod
    def build(
        cls, snapshot_id: str, records: list[dict[str, object]], chunk_size: int = 1_000_000
    ) -> DataSnapshot:
        payload = canonical_snapshot_bytes(records)
        chunks = tuple(
            gzip.compress(payload[offset : offset + chunk_size], mtime=0)
            for offset in range(0, len(payload), chunk_size)
        ) or (gzip.compress(b"[]", mtime=0),)
        return cls(snapshot_id, hashlib.sha256(payload).hexdigest(), len(records), chunks)

    def payload(self) -> bytes:
        payload = b"".join(gzip.decompress(chunk) for chunk in self.compressed_chunks)
        if hashlib.sha256(payload).hexdigest() != self.content_sha256:
            raise ValueError("数据快照摘要不匹配")
        return payload
