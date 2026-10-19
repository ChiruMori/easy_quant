from typing import Any

from easy_quant.application.ports.resource_lifecycle import ResourceLifecycleStore
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError


class ResourceLifecycleService:
    def __init__(self, store: ResourceLifecycleStore) -> None:
        self.store = store

    def inspect(self, kind: str, identifier: str, owner_id: str) -> dict[str, Any]:
        with self.store.transaction() as graph:
            return self._inspect(graph, kind, identifier, owner_id)

    @staticmethod
    def _inspect(graph, kind, identifier, owner_id):
        docs = graph.documents
        instances = docs.get("live_instances", {})
        versions = set()
        runs = set()
        if kind == "strategy":
            item = graph.strategies.get(identifier)
            if item is None or item.owner_id != owner_id:
                raise NotFoundError(kind)
            versions = {key for key, row in graph.versions.items() if row.strategy_id == identifier}
            runs = {
                key
                for key, row in graph.backtests.items()
                if row["strategy_version_id"] in versions
            }
            linked = [
                row
                for row in instances.values()
                if row["strategy_version_id"] in versions or row.get("backtest_id") in runs
            ]
            if linked:
                names = "、".join(str(row.get("name") or row["id"]) for row in linked)
                raise StateConflictError(
                    f"已有实盘在运行或保留数据，不可删除策略：{names}。"
                    "如需删除策略，请先手动删除相关实盘数据（运行或暂停的实盘须先终止）。"
                )
            name = item.name
        elif kind == "live":
            item = instances.get(identifier)
            if item is None or item["owner_id"] != owner_id:
                raise NotFoundError(kind)
            if item["status"] != "terminated":
                raise StateConflictError("仅已终止的实盘允许删除，请先终止实盘")
            name = item.get("name") or identifier
        else:
            item = next(
                (
                    row
                    for row in docs.get("subscriptions", {}).values()
                    if row["id"] == identifier and row["owner_id"] == owner_id
                ),
                None,
            )
            if item is None:
                raise NotFoundError(kind)
            linked = [
                row
                for row in instances.values()
                if row["owner_id"] == owner_id
                and ("subscription_ids" not in row or identifier in row["subscription_ids"])
            ]
            if linked:
                names = "、".join(str(row.get("name") or row["id"]) for row in linked)
                raise StateConflictError(f"通知渠道被以下实盘使用，不可删除：{names}")
            if item.get("enabled", True):
                raise StateConflictError("请先停用通知渠道再删除")
            name = item.get("name") or item["channel"]
        quick = [
            job
            for job in graph.jobs.values()
            if kind == "strategy"
            and job.job_type == "strategy.run"
            and (
                job.payload.get("strategy_id") == identifier
                or job.payload.get("strategy_version_id") in versions
            )
        ]
        related = [
            job
            for job in graph.jobs.values()
            if job in quick
            or (kind == "strategy" and job.payload.get("backtest_id") in runs)
            or (kind == "live" and job.payload.get("instance_id") == identifier)
        ]
        if any(job.status.value == "running" for job in related):
            raise StateConflictError("关联任务正在执行，请等待任务结束后重试删除")
        return {
            "name": name,
            "quick_tests": len(quick),
            "backtests": len(runs),
            "versions": len(versions),
        }

    def delete(self, kind, identifier, owner_id, confirmed, audit):
        with self.store.transaction() as graph:
            summary = self._inspect(graph, kind, identifier, owner_id)
            if not confirmed:
                raise StateConflictError("删除前必须二次确认", summary)
            docs = graph.documents
            removed_deliveries = set()
            if kind == "strategy":
                versions = {
                    key for key, row in graph.versions.items() if row.strategy_id == identifier
                }
                runs = {
                    key
                    for key, row in graph.backtests.items()
                    if row["strategy_version_id"] in versions
                }
                self._remove_jobs(
                    graph,
                    lambda job: (
                        job.payload.get("strategy_id") == identifier
                        or job.payload.get("strategy_version_id") in versions
                        or job.payload.get("backtest_id") in runs
                    ),
                )
                for key in runs:
                    del graph.backtests[key]
                for key in versions:
                    del graph.versions[key]
                del graph.strategies[identifier]
            elif kind == "live":
                recommendations = docs.setdefault("recommendations", {}).pop(identifier, [])
                rec_ids = {row["id"] for row in recommendations}
                operations = docs.setdefault("operations", {})
                operation_keys = {
                    key
                    for key, row in operations.items()
                    if row.get("recommendation_id") in rec_ids
                    or row.get("live_instance_id") == identifier
                }
                op_ids = {operations[key]["id"] for key in operation_keys}
                for key in operation_keys:
                    del operations[key]
                self._remove_docs(
                    docs,
                    "portfolio_ledger",
                    lambda row: (
                        row.get("live_instance_id") == identifier
                        or row.get("operation_id") in op_ids
                    ),
                )
                self._remove_docs(
                    docs,
                    "schedules",
                    lambda row: row.get("configuration", {}).get("instance_id") == identifier,
                )
                removed_deliveries = self._remove_docs(
                    docs,
                    "deliveries",
                    lambda row: (
                        row.get("event_id") in rec_ids
                        or row.get("recommendation_id") in rec_ids
                        or str(row.get("event_id", "")).startswith(f"{identifier}:")
                    ),
                )
                self._remove_jobs(graph, lambda job: job.payload.get("instance_id") == identifier)
                del docs["live_instances"][identifier]
            else:
                self._remove_docs(docs, "subscriptions", lambda row: row["id"] == identifier)
                removed_deliveries = self._remove_docs(
                    docs, "deliveries", lambda row: row.get("subscription_id") == identifier
                )
            self._remove_jobs(
                graph, lambda job: job.payload.get("delivery_id") in removed_deliveries
            )
            docs.setdefault("audit_events", {})[audit["id"]] = audit
            return summary

    @staticmethod
    def _remove_jobs(graph, predicate):
        for key, job in list(graph.jobs.items()):
            if predicate(job):
                if job.status.value == "running":
                    raise StateConflictError("关联任务正在执行，请等待任务结束后重试删除")
                del graph.jobs[key]

    @staticmethod
    def _remove_docs(docs, namespace, predicate):
        rows = docs.setdefault(namespace, {})
        removed = set()
        for key, row in list(rows.items()):
            if predicate(row):
                removed.add(row.get("id", key))
                del rows[key]
        return removed
