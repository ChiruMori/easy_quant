from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from easy_quant.domain.market_data.calendar import TradingCalendar
from easy_quant.domain.scheduling.entities import Job
from easy_quant.infrastructure.core import UuidGenerator
from easy_quant.worker.registry import JobHandlerRegistry


def register_market_data_handlers(
    registry: JobHandlerRegistry, container: Any | None = None
) -> None:
    def enabled_sources(dataset_key: str) -> set[str] | None:
        assert container is not None
        dataset = next(
            (item for item in container.state.datasets if item["key"] == dataset_key), None
        )
        return (
            {str(item["key"]) for item in dataset["sources"] if item.get("enabled", True)}
            if dataset
            else None
        )

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

    def nightly(job: Job) -> dict[str, object]:
        if container is None or container.data_sync is None:
            raise RuntimeError("数据同步服务未配置")
        now = container.authentication.clock.now()
        day = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
        # 先同步日历与证券清单，再以最新清单创建可独立重试的分批任务。
        container.data_sync.sync(
            "trading-calendar", force=True, source_keys=enabled_sources("trading-calendar")
        )
        calendar = TradingCalendar(container.market_data.list_trading_days() or None)
        if not calendar.is_trading_day(day):
            return {"status": "skipped", "reason": "非交易日"}
        container.data_sync.sync(
            "securities", force=True, source_keys=enabled_sources("securities")
        )
        symbols = sorted(
            str(item["symbol"])
            for item in container.market_data.list_instruments()
            if item.get("status", "active") != "delisted"
        )
        coverage = container.market_data.bar_coverage()
        jobs = []
        for dataset in (
            "daily-bars",
            "market-values",
            "pledge-ratios",
            "financial-indicators",
            "sw-industry-memberships",
        ):
            batches = (
                [symbols[index : index + 20] for index in range(0, len(symbols), 20)]
                if dataset in {"daily-bars", "financial-indicators"}
                else [[]]
            )
            for index, batch in enumerate(batches):
                start_day = min(
                    (
                        coverage.get(symbol, {}).get("last_day") or day - timedelta(days=365)
                        for symbol in batch
                    ),
                    default=day,
                )
                if dataset == "financial-indicators":
                    start_day = date(day.year - 5, 1, 1)
                task_id = f"nightly:{day}:{dataset}:{index}"
                payload = {
                    "task_id": task_id,
                    "dataset_key": dataset,
                    "symbols": batch,
                    "start_day": start_day.isoformat(),
                    "end_day": day.isoformat(),
                    "force": True,
                }
                queued = container.jobs.enqueue(
                    Job(UuidGenerator().new(), "market-data-acquisition", task_id, payload, now)
                )
                if task_id not in container.state.acquisitions:
                    container.state.acquisitions[task_id] = {
                        "id": task_id,
                        **payload,
                        "status": "queued",
                        "job_id": queued.id,
                    }
                jobs.append(queued.id)
        return {"status": "queued", "trading_day": day.isoformat(), "child_jobs": jobs}

    registry.register("market-data-nightly", nightly)

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
            if container.database_session is not None:
                container.database_session.rollback()
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
