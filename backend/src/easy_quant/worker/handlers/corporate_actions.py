"""权益补齐逐股续传；数据请求由来源适配器限时，任务间保留请求预算。"""

from datetime import timedelta

from easy_quant.application.ports.jobs import JobContinuation
from easy_quant.application.services.corporate_actions import identity
from easy_quant.application.services.tdx_equity_sync import enrich_tdx_equity, enrichment_due
from easy_quant.domain.market_data.corporate_actions import ZONE
from easy_quant.domain.market_data.research_actions import TDX_PRICE_DATASET
from easy_quant.domain.scheduling.entities import Job


def enqueue_equity_enrichment(container, now):
    publications = container.market_data.list_records(TDX_PRICE_DATASET)
    symbols = sorted(row["symbol"] for row in publications if row["events"])
    signature = identity(
        {
            "day": str(now.astimezone(ZONE).date()),
            "versions": sorted(
                (row["symbol"], [event["record_key"] for event in row["events"]])
                for row in publications
            ),
        }
    )
    job = Job(
        f"equity-{signature[:40]}",
        "tdx-equity-enrichment",
        f"equity:{signature}",
        {"symbols": symbols, "cursor": 0},
        now,
    )
    return container.jobs.enqueue(job)


def register_corporate_action_handlers(registry, container):
    def enrich(job):
        source = container.equity_source
        if source is None:
            raise RuntimeError("公开权益补齐来源未配置")
        now = container.authentication.clock.now()
        symbols, cursor = job.payload["symbols"], int(job.payload.get("cursor", 0))
        if cursor >= len(symbols):
            return {
                "status": "partial"
                if job.payload.get("failed") or job.payload.get("unresolved")
                else "succeeded",
                "completed": cursor,
                "total": len(symbols),
                "added": job.payload.get("added", 0),
                "failed": job.payload.get("failed", []),
                "unresolved": job.payload.get("unresolved", 0),
            }
        symbol = symbols[cursor]
        publications = container.market_data.list_records(TDX_PRICE_DATASET, symbol)
        try:
            if publications and enrichment_due(container.market_data, publications[0], now):
                result = enrich_tdx_equity(container.market_data, source, symbol, now, refresh=True)
                job.payload["added"] = int(job.payload.get("added", 0)) + result["added"]
                job.payload["unresolved"] = int(job.payload.get("unresolved", 0)) + len(
                    result["missing"]
                )
            job.payload["cursor"] = cursor + 1
            job.payload["retries"] = 0
        except (ValueError, RuntimeError):
            retries = int(job.payload.get("retries", 0)) + 1
            job.payload["retries"] = retries
            if retries >= 3:
                job.payload.setdefault("failed", []).append(symbol)
                job.payload["cursor"] = cursor + 1
                job.payload["retries"] = 0
        return JobContinuation(
            {
                "status": "running",
                "completed": job.payload["cursor"],
                "total": len(symbols),
                "added": job.payload.get("added", 0),
                "failed": job.payload.get("failed", []),
                "unresolved": job.payload.get("unresolved", 0),
            },
            now + timedelta(seconds=5),
        )

    registry.register("tdx-equity-enrichment", enrich)
