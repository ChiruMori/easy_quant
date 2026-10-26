from __future__ import annotations

import hashlib
import logging
import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic

from easy_quant.application.ports.core import Clock, Sleeper
from easy_quant.application.ports.market_data import DataSource, RawCache, RetryPolicy
from easy_quant.domain.market_data.entities import (
    AttemptStatus,
    RawEnvelope,
    SemanticRequest,
    SourceAttempt,
)
from easy_quant.domain.shared.errors import DomainError

logger = logging.getLogger(__name__)


class AcquisitionFailed(DomainError):
    def __init__(self, message: str, details: dict[str, object]) -> None:
        super().__init__("all_sources_failed", message, details)


def _safe_source_error(error: Exception) -> str:
    message = str(error)
    message = re.sub(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@", r"\1<redacted>@", message)
    message = re.sub(r"(?i)((?:basic|bearer)\s+)[^\s,;]+", r"\1<redacted>", message)
    message = re.sub(
        r"""(?i)(\b(?:ut|token|api[_-]?key|secret|password|authorization)["']?\s*[:=]\s*)"""
        r"""(?:"[^"]*"|'[^']*'|[^&\s),}]+)""",
        r"\1<redacted>",
        message,
    )
    return " ".join(message.split())[:1000]


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
        validate: Callable[[SemanticRequest, bytes], None] | None = None,
        retry_by_round: bool = False,
    ) -> None:
        self.sources = sources
        self.cache = cache
        self.clock = clock
        self.sleeper = sleeper
        self.retry = retry or ExponentialRetry()
        self.freshness = freshness
        self.shuffle = shuffle
        self.validate = validate
        self.retry_by_round = retry_by_round

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
        sequence = (
            [
                (source, attempt)
                for attempt in range(1, self.retry.max_attempts + 1)
                for source in sources
            ]
            if self.retry_by_round
            else [
                (source, attempt)
                for source in sources
                for attempt in range(1, self.retry.max_attempts + 1)
            ]
        )
        for source, attempt in sequence:
            cache_identity = hashlib.sha256(f"{source.key}:{request.identity}".encode()).hexdigest()
            cached = self.cache.get(cache_identity) if not force and attempt == 1 else None
            if cached and cached.is_valid() and cached.is_fresh(self.clock.now()):
                try:
                    if self.validate:
                        self.validate(request, cached.payload)
                except Exception as error:
                    message = f"{type(error).__name__}: {_safe_source_error(error)}"
                    attempts.append(SourceAttempt(source.key, 0, AttemptStatus.FAILED, message))
                    logger.warning(
                        "数据来源缓存无效 dataset=%s source=%s reason=%s",
                        request.dataset_key,
                        source.key,
                        message,
                    )
                else:
                    attempts.append(
                        SourceAttempt(source.key, 0, AttemptStatus.SUCCEEDED, "命中原始缓存")
                    )
                    return cached, attempts
            started = monotonic()
            logger.info(
                "数据来源请求 dataset=%s source=%s attempt=%s max_attempts=%s",
                request.dataset_key,
                source.key,
                attempt,
                self.retry.max_attempts,
            )
            try:
                payload, content_type = source.fetch(request)
                if self.validate:
                    self.validate(request, payload)
                now = self.clock.now()
                envelope = RawEnvelope(
                    cache_identity, source.key, payload, content_type, now, now + self.freshness
                )
            except Exception as error:
                message = f"{type(error).__name__}: {_safe_source_error(error)}"
                attempts.append(SourceAttempt(source.key, attempt, AttemptStatus.FAILED, message))
                logger.warning(
                    "数据来源失败 dataset=%s source=%s attempt=%s seconds=%.3f reason=%s",
                    request.dataset_key,
                    source.key,
                    attempt,
                    monotonic() - started,
                    message,
                )
                if attempt < self.retry.max_attempts and (
                    not self.retry_by_round or source is sources[-1]
                ):
                    self.sleeper.sleep(self.retry.delay_seconds(attempt))
                continue
            # Persistence failures are infrastructure failures, not a reason to refetch.
            self.cache.put(envelope)
            attempts.append(SourceAttempt(source.key, attempt, AttemptStatus.SUCCEEDED))
            logger.info(
                "数据来源成功 dataset=%s source=%s attempt=%s seconds=%.3f",
                request.dataset_key,
                source.key,
                attempt,
                monotonic() - started,
            )
            return envelope, attempts
        logger.error(
            "数据来源耗尽 dataset=%s sources=%s attempts=%s",
            request.dataset_key,
            len(sources),
            len(attempts),
        )
        raise AcquisitionFailed(
            "所有数据来源均失败",
            details={
                "dataset": request.dataset_key,
                "attempts": [
                    {
                        "source_key": item.source_key,
                        "attempt": item.attempt,
                        "status": item.status.value,
                        "message": item.message,
                    }
                    for item in attempts
                ],
            },
        )
