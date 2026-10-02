from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any

from easy_quant.worker.registry import JobHandlerRegistry


def register_market_data_handlers(
    registry: JobHandlerRegistry, container: Any | None = None
) -> None:
    def update_tdx(job):
        if container is None or container.tdx_daily is None:
            raise RuntimeError("通达信增量更新服务未配置")
        payload = job.payload
        result = container.tdx_daily.update(
            start_day=date.fromisoformat(str(payload["start_day"]))
            if payload.get("start_day")
            else None,
            end_day=date.fromisoformat(str(payload["end_day"])) if payload.get("end_day") else None,
        )
        if result.unresolved:
            dates = ",".join(item["day"] for item in result.unresolved)
            raise RuntimeError(f"通达信增量存在未解决日期：{dates}；下次运行自动重试")
        return {**asdict(result), "status": "succeeded"}

    registry.register("tdx-daily-update", update_tdx)

    def acquire(job):
        if container is None or container.data_sync is None:
            raise RuntimeError("数据同步服务未配置")
        payload = job.payload
        task_id = str(payload.get("task_id", ""))
        task = container.state.acquisitions.get(task_id) if task_id else None
        if task is not None:
            task["status"] = "running"
            container.state.acquisitions[task_id] = task
        try:
            dataset = next(
                (
                    item
                    for item in container.state.datasets
                    if item["key"] == str(payload.get("dataset_key", "daily-bars"))
                ),
                None,
            )
            enabled_sources = (
                {str(item["key"]) for item in dataset["sources"] if item.get("enabled", True)}
                if dataset
                else None
            )
            result = container.data_sync.sync(
                str(payload.get("dataset_key", "daily-bars")),
                symbols=[str(item) for item in payload.get("symbols", [])],
                start_day=date.fromisoformat(str(payload["start_day"]))
                if payload.get("start_day")
                else None,
                end_day=date.fromisoformat(str(payload["end_day"]))
                if payload.get("end_day")
                else None,
                force=bool(payload.get("force", False)),
                source_keys=enabled_sources,
            )
        except Exception as error:
            if task is not None:
                task.update({"status": "failed", "message": str(error)})
                details = getattr(error, "details", None)
                if isinstance(details, dict):
                    task["attempts"] = details.get("attempts", [])
                container.state.acquisitions[task_id] = task
            raise
        if task is not None:
            task.update(result)
            task["status"] = "succeeded"
            container.state.acquisitions[task_id] = task
        return {**result, "status": "succeeded", "task_id": task_id}

    registry.register("market-data-acquisition", acquire)
    registry.register("market-data.acquire", acquire)
    registry.register(
        "market-data.reparse", lambda job: {"request": job.payload, "status": "reparsed"}
    )
    registry.register(
        "market-data.import", lambda job: {"request": job.payload, "status": "imported"}
    )
