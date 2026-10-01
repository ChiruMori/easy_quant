from __future__ import annotations

from typing import Any

from easy_quant.infrastructure.core import UuidGenerator


def record_audit(
    container: Any,
    *,
    actor_user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
    trigger_source: str = "api",
) -> None:
    container.state.audit_events.append(
        {
            "id": UuidGenerator().new(),
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "occurred_at": container.authentication.clock.now().isoformat(),
            "trigger_source": trigger_source,
            "actor_user_id": actor_user_id,
            "before_summary": before or {},
            "after_summary": after or {},
        }
    )
