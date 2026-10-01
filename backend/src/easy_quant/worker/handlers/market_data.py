from __future__ import annotations

from datetime import date
from typing import Any

from easy_quant.worker.registry import JobHandlerRegistry


def register_market_data_handlers(
    registry: JobHandlerRegistry, container: Any | None = None
) -> None:
    def acquire(job):
        if container is None or container.data_sync is None:
            return {"request": job.payload, "status": "queued"}
        payload = job.payload
        result = container.data_sync.sync(
            str(payload.get("dataset_key", "daily-bars")),
            symbols=[str(item) for item in payload.get("symbols", [])],
            start_day=date.fromisoformat(str(payload["start_day"]))
            if payload.get("start_day")
            else None,
            end_day=date.fromisoformat(str(payload["end_day"])) if payload.get("end_day") else None,
            force=bool(payload.get("force", False)),
        )
        return {**result, "status": "succeeded"}

    registry.register("market-data-acquisition", acquire)
    registry.register("market-data.acquire", acquire)
    registry.register(
        "market-data.reparse", lambda job: {"request": job.payload, "status": "reparsed"}
    )
    registry.register(
        "market-data.import", lambda job: {"request": job.payload, "status": "imported"}
    )
