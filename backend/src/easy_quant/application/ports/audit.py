from __future__ import annotations

from datetime import datetime
from typing import Protocol

from easy_quant.domain.audit.entities import AuditEvent


class AuditRepository(Protocol):
    def append(self, event: AuditEvent) -> None: ...

    def query(
        self,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        actor_user_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]: ...
