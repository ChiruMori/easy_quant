from __future__ import annotations

import gzip
import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from easy_quant.domain.market_data.entities import RawEnvelope
from easy_quant.infrastructure.persistence.models.market_data_catalog import RawCacheModel


@dataclass(slots=True)
class StoredRawEnvelope:
    metadata: RawEnvelope
    compressed_payload: bytes


class InMemoryCompressedRawCache:
    """可替换为 SQLAlchemy blob 仓储；保持转换前字节和摘要。"""

    def __init__(self) -> None:
        self._items: dict[str, StoredRawEnvelope] = {}

    def put(self, envelope: RawEnvelope) -> None:
        if hashlib.sha256(envelope.payload).hexdigest() != envelope.payload_sha256:
            raise ValueError("原始响应摘要不匹配")
        self._items[envelope.request_identity] = StoredRawEnvelope(
            envelope, gzip.compress(envelope.payload, mtime=0)
        )

    def get(self, request_identity: str) -> RawEnvelope | None:
        stored = self._items.get(request_identity)
        if stored is None:
            return None
        stored.metadata.payload = gzip.decompress(stored.compressed_payload)
        return stored.metadata if stored.metadata.is_valid() else None


class SqlAlchemyCompressedRawCache:
    def __init__(self, session: Session) -> None:
        self.session = session

    def put(self, envelope: RawEnvelope) -> None:
        if hashlib.sha256(envelope.payload).hexdigest() != envelope.payload_sha256:
            raise ValueError("原始响应摘要不匹配")
        self.session.merge(
            RawCacheModel(
                request_identity=envelope.request_identity,
                source_key=envelope.source_key,
                payload_gzip=gzip.compress(envelope.payload, mtime=0),
                payload_sha256=envelope.payload_sha256,
                fetched_at=envelope.fetched_at,
                expires_at=envelope.expires_at,
            )
        )
        self.session.commit()

    def get(self, request_identity: str) -> RawEnvelope | None:
        row = self.session.get(RawCacheModel, request_identity)
        if row is None:
            return None
        envelope = RawEnvelope(
            request_identity=row.request_identity,
            source_key=row.source_key,
            payload=gzip.decompress(row.payload_gzip),
            content_type="application/json",
            fetched_at=row.fetched_at,
            expires_at=row.expires_at,
            payload_sha256=row.payload_sha256,
        )
        return envelope if envelope.is_valid() else None
