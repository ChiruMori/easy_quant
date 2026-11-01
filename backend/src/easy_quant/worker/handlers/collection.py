"""一个任务逐页推进；游标随领取结果原子保存，不创建子任务。"""

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from easy_quant.application.ports.jobs import JobContinuation
from easy_quant.application.services.acquisition import AcquisitionFailed, _safe_source_error
from easy_quant.application.services.financial_sync import save_financial_rows
from easy_quant.domain.market_data.calendar import TradingCalendar
from easy_quant.domain.market_data.fundamentals import FINANCIAL_DATASETS
from easy_quant.domain.market_data.indices import is_index

logger = logging.getLogger(__name__)


def units(day):
    periods = [
        date(year, month, end).isoformat()
        for year in range(day.year - 5, day.year + 1)
        for month, end in ((3, 31), (6, 30), (9, 30), (12, 31))
        if date(year, month, end) < day
    ]
    periods.reverse()
    result = [{"dataset": key, "period": ""} for key in ("trading-calendar", "securities")]
    # 最新一期先覆盖全部股票，再补历史。股东与分红同样按报告期批量。
    for index, period in enumerate(periods):
        for key in (
            "balance-sheets",
            "income-statements",
            "cash-flow-statements",
            "financial-indicators",
        ):
            result.append({"dataset": key, "period": period})
        if index == 0:
            result.append({"dataset": "company-profiles", "period": ""})
        for key in ("dividend-plans", "shareholder-counts"):
            result.append({"dataset": key, "period": period})
    result.extend(
        {"dataset": key, "period": ""}
        for key in (
            "trading-status",
            "daily-bars",
            "market-values",
            "pledge-ratios",
            "sw-industry-memberships",
            "business-compositions",
        )
    )
    return result


def collect(container, job, enabled_sources):
    now = container.authentication.clock.now()
    day = date.fromisoformat(
        job.payload.get("end_day") or now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    )
    state = job.payload.setdefault(
        "collection",
        {
            "day": day.isoformat(),
            "bar_day": min(
                day,
                TradingCalendar(container.market_data.list_trading_days() or None)
                .freshness(first_day=None, last_day=None, now=now)
                .recommended_end_day,
            ).isoformat(),
            "unit": 0,
            "page": 1,
            "records": 0,
            "unchanged": 0,
            "failed": [],
            "last_symbol": "",
            "retries": 0,
        },
    )
    day = date.fromisoformat(state["day"])
    work = units(day)
    if state["unit"] >= len(work):
        result = summary(state, work, "采集范围处理完成")
        if state["failed"]:
            raise AcquisitionFailed("采集部分失败；已保存成功范围，详见聚合任务进度", result)
        return result
    unit = work[state["unit"]]
    dataset, period = unit["dataset"], unit["period"]
    checkpoint_key = f"{dataset}:{period}"
    checkpoints = container.collection_checkpoints
    previous = checkpoints.get(checkpoint_key)
    # 最新两个季度每日复查；旧报告30天、概况7天、主营30天复查。
    recent = period and (day - date.fromisoformat(period)).days <= 190
    ttl = timedelta(
        days=1
        if recent or dataset not in FINANCIAL_DATASETS
        else 7
        if dataset == "company-profiles"
        else 30
    )
    fresh = previous and now - datetime.fromisoformat(previous["completed_at"]) < ttl
    done = False
    candidates, symbol = [], ""
    try:
        sources = enabled_sources(dataset)
        if sources == set() or (fresh and state["page"] == 1 and not state["last_symbol"]):
            done = True
        elif dataset in FINANCIAL_DATASETS and dataset != "business-compositions":
            if sources is not None and "eastmoney" not in sources:
                raise ValueError("批量采集需要启用东方财富来源；未自动回退逐股洪泛")
            symbols = {
                str(row["symbol"])
                for row in container.market_data.list_instruments()
                if not is_index(str(row["symbol"]))
            }
            if not symbols:
                raise ValueError("证券清单为空，不能确认批量财务覆盖")
            response = container.financial_bulk.page(dataset, period, state["page"], symbols)
            rows, pages, count = response
            if state["page"] > 1 and state.get("expected") != count:
                raise ValueError("来源分页总量变化；保留已保存记录，等待重试")
            fingerprint = getattr(response, "fingerprint", None)
            if (
                fingerprint
                and count
                and (
                    fingerprint in state.get("page_fingerprints", [])
                    or getattr(response, "first_code", "") < state.get("page_last_code", "")
                )
            ):
                raise ValueError("批量来源分页重复或回退，不能确认完整覆盖")
            matched = state.get("matched", 0) + len(rows)
            if state["page"] >= pages and count > 0 and matched == 0:
                raise ValueError("来源有记录但未匹配已知股票，不能确认覆盖")
            state["matched"] = matched
            added, same = save_financial_rows(
                container.market_data, dataset, rows, "eastmoney", now
            )
            state["records"] += added
            state["unchanged"] += same
            if fingerprint and count:
                state.setdefault("page_fingerprints", []).append(fingerprint)
                state["page_last_code"] = response.last_code
            state["expected"], state["pages"] = count, pages
            state["page"] += 1
            done = state["page"] > pages
        elif dataset in {"daily-bars", "business-compositions"}:
            if sources is not None and "eastmoney" not in sources:
                raise ValueError("串行自动采集需要启用受请求预算控制的东方财富来源")
            instruments = sorted(
                container.market_data.list_instruments(), key=lambda row: row["symbol"]
            )
            candidates = [
                row
                for row in instruments
                if str(row["symbol"]) > state["last_symbol"]
                and row.get("status") != "delisted"
                and (dataset == "daily-bars" or not is_index(str(row["symbol"])))
                and (dataset != "daily-bars" or row.get("status") != "suspended")
            ]
            if not candidates:
                done = True
            else:
                symbol = str(candidates[0]["symbol"])
                key = f"{dataset}:{symbol}"
                last = checkpoints.get(key)
                if not last or now - datetime.fromisoformat(last["completed_at"]) >= timedelta(
                    days=1 if dataset == "daily-bars" else 30
                ):
                    start = date(day.year - 5, 1, 1)
                    if dataset == "daily-bars":
                        bounds = container.market_data.bar_coverage([symbol]).get(symbol, {})
                        day = date.fromisoformat(state["bar_day"])
                        start = bounds.get("last_day") or day - timedelta(days=365)
                    if start < day or dataset != "daily-bars":
                        result = container.data_sync.sync(
                            dataset,
                            symbols=[symbol],
                            start_day=start,
                            end_day=day,
                            force=True,
                            source_keys=(
                                {"eastmoney"} & sources if sources is not None else {"eastmoney"}
                            ),
                        )
                        state["records"] += int(result.get("record_count", 0))
                    checkpoints[key] = {"completed_at": now.isoformat()}
                state["last_symbol"] = symbol
        else:
            result = container.data_sync.sync(
                dataset,
                force=True,
                end_day=date.fromisoformat(state["bar_day"])
                if dataset == "trading-status"
                else now.astimezone(ZoneInfo("Asia/Shanghai")).date()
                if dataset in {"market-values", "sw-industry-memberships"}
                else day,
                source_keys=({"eastmoney"} & sources if sources is not None else {"eastmoney"})
                if dataset == "securities"
                else sources,
                **(
                    {"confirmation_source_keys": {"eastmoney"}}
                    if dataset == "trading-status"
                    else {}
                ),
            )
            state["records"] += int(result.get("record_count", 0))
            if dataset == "trading-calendar":
                state["bar_day"] = min(
                    day,
                    TradingCalendar(container.market_data.list_trading_days() or None)
                    .freshness(first_day=None, last_day=None, now=now)
                    .recommended_end_day,
                ).isoformat()
            done = True
        state["retries"] = 0
    except Exception as error:
        if container.database_session is not None:
            container.database_session.rollback()
        state["retries"] += 1
        if state["retries"] < 3:
            return JobContinuation(
                summary(state, work, "来源失败，限频退避后重试"),
                now + timedelta(minutes=5 * state["retries"]),
            )
        state["failed_count"] = state.get("failed_count", 0) + 1
        state["failed"] = state["failed"][:19]
        state["failed"].append(
            {**unit, "symbol": symbol or state["last_symbol"], "message": _safe_source_error(error)}
        )
        if dataset in {"daily-bars", "business-compositions"} and candidates:
            state["last_symbol"] = symbol
            state["retries"] = 0
            state["had_failure"] = True
        else:
            done = True
    if done:
        logger.info(
            "聚合采集范围已处理 job_id=%s dataset=%s period=%s records=%s failures=%s",
            job.id,
            dataset,
            period,
            state["records"],
            state.get("failed_count", 0),
        )
        if not state["retries"] and not state.get("had_failure"):
            checkpoints[checkpoint_key] = {"completed_at": now.isoformat()}
        state.update(unit=state["unit"] + 1, page=1, last_symbol="", retries=0)
        state.pop("matched", None)
        state.pop("page_fingerprints", None)
        state.pop("page_last_code", None)
        state.pop("had_failure", None)
        state.pop("expected", None)
        state.pop("pages", None)
    return JobContinuation(
        summary(state, work, "串行采集中；每次请求至少间隔5秒"), now + timedelta(seconds=5)
    )


def summary(state, work, message):
    current = work[state["unit"]] if state["unit"] < len(work) else {}
    return {
        "collection": True,
        "message": message,
        "completed_units": state["unit"],
        "total_units": len(work),
        "dataset_key": current.get("dataset", ""),
        "report_period": current.get("period", ""),
        "page": state["page"],
        "pages": state.get("pages"),
        "last_symbol": state["last_symbol"],
        "record_count": state["records"],
        "unchanged_count": state["unchanged"],
        "failed_datasets": state["failed"],
        "failed_count": state.get("failed_count", 0),
    }
