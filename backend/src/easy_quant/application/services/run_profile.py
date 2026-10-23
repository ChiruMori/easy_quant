from collections.abc import Callable
from time import perf_counter
from typing import Any


class RunProfile:
    """宿主观测耗时；不参与领域计算及可复现输入身份。"""

    def __init__(self, timer: Callable[[], float] = perf_counter) -> None:
        self.timer = timer
        self.started = timer()
        self.stage_started = self.started
        self.stage = "validation"
        self.stages: dict[str, float] = {}
        self.hooks: list[dict[str, Any]] = []
        self.workload: dict[str, Any] = {}

    def enter(self, stage: str) -> None:
        now = self.timer()
        self.stages[self.stage] = self.stages.get(self.stage, 0) + now - self.stage_started
        self.stage, self.stage_started = stage, now

    def record_hook(self, day: str, hook: str, started: float) -> None:
        self.hooks.append(
            {"trading_day": day, "hook": hook, "seconds": round(self.timer() - started, 6)}
        )

    def snapshot(self) -> dict[str, Any]:
        now = self.timer()
        stages = {**self.stages}
        stages[self.stage] = stages.get(self.stage, 0) + now - self.stage_started
        summary = {}
        for hook in ("before_market", "on_market", "after_market"):
            values = [item["seconds"] for item in self.hooks if item["hook"] == hook]
            summary[hook] = {
                "count": len(values),
                "total_seconds": round(sum(values), 6),
                "average_seconds": round(sum(values) / len(values), 6) if values else 0,
                "max_seconds": max(values, default=0),
            }
        return {
            "total_seconds": round(now - self.started, 6),
            "stages": {key: round(value, 6) for key, value in stages.items()},
            "hooks": summary,
            "daily_hooks": list(self.hooks),
            "measurement": "host-wall-time-including-ipc-v1",
            "workload": dict(self.workload),
        }
