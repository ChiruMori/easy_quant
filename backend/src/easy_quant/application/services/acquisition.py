from __future__ import annotations

import hashlib
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from easy_quant.application.ports.core import Clock, Sleeper
from easy_quant.application.ports.market_data import DataSource, RawCache, RetryPolicy
from easy_quant.domain.market_data.entities import (
    AttemptStatus,
    RawEnvelope,
    SemanticRequest,
    SourceAttempt,
)
from easy_quant.domain.shared.errors import DomainError


class AcquisitionFailed(DomainError):
    def __init__(self, message: str, details: dict[str, object]) -> None:
        super().__init__("all_sources_failed", message, details)


@dataclass(frozen=True, slots=True)
class ExponentialRetry:
    max_attempts: int = 3
    base_seconds: float = 0.25

    def delay_seconds(self, attempt: int) -> float:
        return self.base_seconds * 2 ** (attempt - 1)


class AcquisitionService:
    def __init__(
        self,
        sources: list[DataSource],
        cache: RawCache,
        clock: Clock,
        sleeper: Sleeper,
        retry: RetryPolicy | None = None,
        freshness: timedelta = timedelta(hours=6),
        shuffle: Callable[[list[DataSource]], None] = random.shuffle,
    ) -> None:
        self.sources = sources
        self.cache = cache
        self.clock = clock
        self.sleeper = sleeper
        self.retry = retry or ExponentialRetry()
        self.freshness = freshness
        self.shuffle = shuffle

    def acquire(self, request: SemanticRequest, *, force: bool = False) -> RawEnvelope:
        envelope, _ = self.acquire_with_attempts(request, force=force)
        return envelope

    def acquire_with_attempts(
        self,
        request: SemanticRequest,
        *,
        force: bool = False,
        source_keys: set[str] | None = None,
    ) -> tuple[RawEnvelope, list[SourceAttempt]]:
        attempts: list[SourceAttempt] = []
        sources = [
            source for source in self.sources if source_keys is None or source.key in source_keys
        ]
        self.shuffle(sources)
        for source in sources:
            cache_identity = hashlib.sha256(f"{source.key}:{request.identity}".encode()).hexdigest()
            cached = self.cache.get(cache_identity)
            if not force and cached and cached.is_valid() and cached.is_fresh(self.clock.now()):
                attempts.append(
                    SourceAttempt(source.key, 0, AttemptStatus.SUCCEEDED, "命中原始缓存")
                )
                return cached, attempts
            for attempt in range(1, self.retry.max_attempts + 1):
                try:
                    payload, content_type = source.fetch(request)
                    now = self.clock.now()
                    envelope = RawEnvelope(
                        cache_identity,
                        source.key,
                        payload,
                        content_type,
                        now,
                        now + self.freshness,
                    )
                    self.cache.put(envelope)
                    attempts.append(SourceAttempt(source.key, attempt, AttemptStatus.SUCCEEDED))
                    return envelope, attempts
                except Exception as error:  # 来源适配器错误在边界统一汇总
                    attempts.append(
                        SourceAttempt(source.key, attempt, AttemptStatus.FAILED, str(error))
                    )
                    if attempt < self.retry.max_attempts:
                        self.sleeper.sleep(self.retry.delay_seconds(attempt))
        raise AcquisitionFailed(
            "所有数据来源均失败",
            details={
                "attempts": [
                    {
                        "source_key": item.source_key,
                        "attempt": item.attempt,
                        "status": item.status.value,
                        "message": item.message,
                    }
                    for item in attempts
                ]
            },
        )
