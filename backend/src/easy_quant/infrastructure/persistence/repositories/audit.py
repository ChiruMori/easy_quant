from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from easy_quant.domain.audit.entities import AuditEvent
from easy_quant.infrastructure.persistence.models.audit import AuditEventModel


class SqlAlchemyAuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, event: AuditEvent) -> None:
        self.session.add(
            AuditEventModel(
                id=event.id,
                action=event.action,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                occurred_at=event.occurred_at,
                trigger_source=event.trigger_source,
                actor_user_id=event.actor_user_id,
                correlation_id=event.correlation_id,
                before_summary=event.before_summary,
                after_summary=event.after_summary,
            )
        )

    def query(
        self,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        actor_user_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        statement = select(AuditEventModel)
        if resource_type is not None:
            statement = statement.where(AuditEventModel.resource_type == resource_type)
        if resource_id is not None:
            statement = statement.where(AuditEventModel.resource_id == resource_id)
        if actor_user_id is not None:
            statement = statement.where(AuditEventModel.actor_user_id == actor_user_id)
        if since is not None:
            statement = statement.where(AuditEventModel.occurred_at >= since)
        rows = self.session.scalars(
            statement.order_by(AuditEventModel.occurred_at.desc()).limit(min(limit, 200))
        )
        return [
            AuditEvent(
                id=row.id,
                action=row.action,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                occurred_at=row.occurred_at,
                trigger_source=row.trigger_source,
                actor_user_id=row.actor_user_id,
                correlation_id=row.correlation_id,
                before_summary=row.before_summary,
                after_summary=row.after_summary,
            )
            for row in rows
        ]
