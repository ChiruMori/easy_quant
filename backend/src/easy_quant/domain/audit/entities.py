from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from easy_quant.domain.shared.value_objects import ensure_utc


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: str
    action: str
    resource_type: str
    resource_id: str
    occurred_at: datetime
    trigger_source: str
    actor_user_id: str | None = None
    correlation_id: str | None = None
    before_summary: dict[str, Any] = field(default_factory=dict)
    after_summary: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", ensure_utc(self.occurred_at))
