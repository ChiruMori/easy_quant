from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from easy_quant.domain.shared.value_objects import ensure_utc


class AttemptStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    key: str
    name: str
    schema_version: str


@dataclass(frozen=True, slots=True)
class SourceBinding:
    dataset_key: str
    source_key: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class SemanticRequest:
    dataset_key: str
    parameters: dict[str, object]
    identity: str


@dataclass(slots=True)
class RawEnvelope:
    request_identity: str
    source_key: str
    payload: bytes
    content_type: str
    fetched_at: datetime
    expires_at: datetime
    payload_sha256: str = ""

    def __post_init__(self) -> None:
        self.fetched_at = ensure_utc(self.fetched_at)
        self.expires_at = ensure_utc(self.expires_at)
        if not self.payload_sha256:
            self.payload_sha256 = hashlib.sha256(self.payload).hexdigest()

    def is_fresh(self, now: datetime) -> bool:
        return ensure_utc(now) < self.expires_at

    def is_valid(self) -> bool:
        return hashlib.sha256(self.payload).hexdigest() == self.payload_sha256


@dataclass(slots=True)
class SourceAttempt:
    source_key: str
    attempt: int
    status: AttemptStatus
    message: str | None = None


@dataclass(slots=True)
class AcquisitionRun:
    id: str
    request: SemanticRequest
    started_at: datetime
    attempts: list[SourceAttempt] = field(default_factory=list)
    completed_at: datetime | None = None
    source_key: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.source_key is not None


DEFAULT_FRESHNESS = timedelta(hours=6)
