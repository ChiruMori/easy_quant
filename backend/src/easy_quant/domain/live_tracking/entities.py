from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.shared.value_objects import ensure_utc


class LiveStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    TERMINATED = "terminated"


class RecommendationStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CORRECTED = "corrected"


@dataclass(slots=True)
class LiveInstance:
    id: str
    owner_id: str
    backtest_id: str
    strategy_version_id: str
    status: LiveStatus
    next_decision_at: datetime
    parameters: dict[str, object]

    def pause(self) -> None:
        if self.status is not LiveStatus.ACTIVE:
            raise StateConflictError("仅运行中的实盘可以暂停")
        self.status = LiveStatus.PAUSED

    def resume(self) -> None:
        if self.status is not LiveStatus.PAUSED:
            raise StateConflictError("仅暂停的实盘可以恢复")
        self.status = LiveStatus.ACTIVE

    def terminate(self) -> None:
        if self.status is LiveStatus.TERMINATED:
            return
        self.status = LiveStatus.TERMINATED


def recommendation_business_key(
    live_instance_id: str,
    strategy_version_id: str,
    decision_at: datetime,
    instrument_id: str,
    signal_key: str,
) -> str:
    canonical = "|".join(
        (
            live_instance_id,
            strategy_version_id,
            ensure_utc(decision_at).isoformat(),
            instrument_id,
            signal_key,
        )
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(slots=True)
class Recommendation:
    id: str
    live_instance_id: str
    owner_id: str
    strategy_version_id: str
    decision_at: datetime
    instrument_id: str
    signal_key: str
    action: str
    quantity: str
    reason: str
    business_key: str
    status: RecommendationStatus = RecommendationStatus.PENDING
    version: int = 0
