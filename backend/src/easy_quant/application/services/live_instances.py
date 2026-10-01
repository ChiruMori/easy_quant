from __future__ import annotations

from datetime import datetime
from typing import cast

from easy_quant.application.ports.core import IdGenerator
from easy_quant.domain.live_tracking.entities import LiveInstance, LiveStatus
from easy_quant.domain.shared.errors import StateConflictError


class LiveInstanceService:
    def __init__(self, ids: IdGenerator) -> None:
        self.ids = ids
        self.instances: dict[str, LiveInstance] = {}

    def start(
        self, owner_id: str, backtest: dict[str, object], next_decision_at: datetime
    ) -> LiveInstance:
        if backtest.get("status") != "succeeded":
            raise StateConflictError("只能从成功回测启动实盘")
        parameters = cast(dict[str, object], backtest.get("parameters", {}))
        instance = LiveInstance(
            self.ids.new(),
            owner_id,
            str(backtest["id"]),
            str(backtest["strategy_version_id"]),
            LiveStatus.ACTIVE,
            next_decision_at,
            dict(parameters),
        )
        self.instances[instance.id] = instance
        return instance

    def pause(self, instance_id: str) -> LiveInstance:
        instance = self.instances[instance_id]
        instance.pause()
        return instance

    def terminate(self, instance_id: str) -> LiveInstance:
        instance = self.instances[instance_id]
        instance.terminate()
        return instance
