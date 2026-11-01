from __future__ import annotations

from dataclasses import asdict
from datetime import date, time, timedelta
from typing import Any

from easy_quant.application.services.acquisition import _safe_source_error
from easy_quant.domain.market_data.calendar import TradingCalendar
from easy_quant.domain.market_data.indices import INDEX_CATALOG
from easy_quant.domain.scheduling.entities import Job
from easy_quant.domain.shared.errors import ValidationError
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

    def nightly(job):
        from easy_quant.worker.handlers.collection import collect

        if container is None or container.data_sync is None:
            raise RuntimeError("数据同步服务未配置")
        return collect(container, job, enabled_sources)

    registry.register("market-data-nightly", nightly)
    registry.register("market-data-collection", nightly)

    def acquire(job) -> dict[str, object]:
        if container is None or container.data_sync is None:
            raise RuntimeError("数据同步服务未配置")
        payload = job.payload
        task_id = str(payload.get("task_id", ""))
        if task_id.startswith("nightly:"):
            return {"status": "skipped", "skipped": "旧版分散采集任务已停用，请运行盘后聚合采集"}
        task = container.state.acquisitions.get(task_id) if task_id else None
        if task is not None:
            task["status"] = "running"
            task.pop("retry_at", None)
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
            selected_sources = (
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
                source_keys=selected_sources,
                **(
                    {"confirmation_source_keys": enabled_sources("daily-bars")}
                    if payload.get("dataset_key") == "trading-status"
                    else {}
                ),
            )
        except Exception as error:
            if container.database_session is not None:
                container.database_session.rollback()
            if task is not None:
                # 指数专项内联调用没有独立租约/队列，不能显示永远不会执行的重试。
                retrying = job.job_type == "market-data-acquisition" and 0 < job.attempt_count < 3
                task.update(
                    {
                        "status": "queued" if retrying else "failed",
                        "message": f"{_safe_source_error(error)}；等待自动重试"
                        if retrying
                        else _safe_source_error(error),
                    }
                )
                if retrying:
                    task["retry_at"] = (
                        container.authentication.clock.now()
                        + timedelta(minutes=5 * job.attempt_count)
                    ).isoformat()
                details = getattr(error, "details", None)
                if isinstance(details, dict):
                    task["attempts"] = details.get("attempts", [])
                    for key in ("record_count", "new_record_count", "failed_symbols"):
                        if key in details:
                            task[key] = details[key]
                container.state.acquisitions[task_id] = task
            raise
        if task is not None:
            task.update(result)
            task["status"] = "succeeded"
            container.state.acquisitions[task_id] = task
        return {**result, "status": "succeeded", "task_id": task_id}

    registry.register("market-data-acquisition", acquire)

    def update_indices(job):
        if container is None or container.data_sync is None:
            raise RuntimeError("数据同步服务未配置")
        from easy_quant.application.services.scheduled_tasks import validate_index_configuration

        validate_index_configuration(job.payload)
        now = container.authentication.clock.now()
        calendar = TradingCalendar(container.market_data.list_trading_days() or None)
        end = (
            date.fromisoformat(job.payload["end_day"])
            if job.payload.get("end_day")
            else calendar.freshness(
                first_day=None,
                last_day=None,
                now=now,
                close_time=time(15, 0),
            ).recommended_end_day
        )
        symbols = job.payload.get("symbols", list(INDEX_CATALOG))
        coverage = container.market_data.bar_coverage(symbols)
        count = 0
        failures = []
        for symbol in symbols:
            start = (
                date.fromisoformat(job.payload["start_day"])
                if job.payload.get("start_day")
                else min(coverage.get(symbol, {}).get("last_day") or date(end.year - 10, 1, 1), end)
            )
            if start > end:
                raise ValidationError("开始日期不得晚于结束日期")
            task_id = f"index:{job.id}:{symbol}"
            payload = {
                "task_id": task_id,
                "dataset_key": "daily-bars",
                "symbols": [symbol],
                "start_day": start.isoformat(),
                "end_day": end.isoformat(),
                "force": True,
            }
            container.state.acquisitions[task_id] = {
                "id": task_id,
                **payload,
                "status": "queued",
                "job_id": job.id,
            }
            try:
                result = acquire(Job(job.id, "market-data-acquisition", task_id, payload, now))
                count += int(str(result.get("record_count", 0)))
            except Exception as error:
                failures.append({"symbol": symbol, "message": str(error)})
        if failures:
            names = "、".join(item["symbol"] for item in failures)
            raise ValidationError(
                f"指数同步部分失败：{names}；已完成 {count} 条，请查看数据获取明细后重试",
                {"record_count": count, "failed_symbols": failures},
            )
        return {
            "status": "succeeded",
            "record_count": count,
            "symbols": symbols,
            "end_day": end.isoformat(),
        }

    registry.register("index-daily-update", update_indices)
    registry.register("market-data.acquire", acquire)
    registry.register(
        "market-data.reparse", lambda job: {"request": job.payload, "status": "reparsed"}
    )
    registry.register(
        "market-data.import", lambda job: {"request": job.payload, "status": "imported"}
    )
