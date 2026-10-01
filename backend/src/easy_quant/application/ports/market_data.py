from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Protocol

from easy_quant.domain.market_data.entities import RawEnvelope, SemanticRequest


class DataSource(Protocol):
    key: str

    def fetch(self, request: SemanticRequest) -> tuple[bytes, str]: ...


class RawCache(Protocol):
    def get(self, request_identity: str) -> RawEnvelope | None: ...

    def put(self, envelope: RawEnvelope) -> None: ...


class NormalizedRecordRepository(Protocol):
    def upsert_many(self, dataset_key: str, rows: Iterable[Mapping[str, object]]) -> int: ...


class UploadReader(Protocol):
    def rows(self, content: bytes) -> Iterable[Mapping[str, object]]: ...


class RateGate(Protocol):
    def wait(self, source_key: str, now: datetime) -> None: ...


class RetryPolicy(Protocol):
    @property
    def max_attempts(self) -> int: ...

    def delay_seconds(self, attempt: int) -> float: ...
