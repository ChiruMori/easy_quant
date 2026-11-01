import hashlib
import json
from datetime import date, datetime

from easy_quant.application.services.acquisition import AcquisitionFailed
from easy_quant.domain.market_data.fundamentals import FINANCIAL_DATASETS


def sync_financial(
    service,
    dataset: str,
    symbols: list[str],
    start: date | None,
    end: date,
    force: bool,
    source_keys: set[str] | None,
):
    if not symbols:
        raise ValueError("同步财报和基本面需要指定股票")
    attempts, failures, sources = [], [], set()
    saved = unchanged = 0
    for symbol in sorted(set(symbols)):
        try:
            rows, current_attempts, source, fetched = service._acquire(
                dataset,
                {
                    "symbol": symbol,
                    "start_date": start.isoformat() if start else "1990-01-01",
                    "end_date": end.isoformat(),
                },
                force,
                source_keys,
            )
            attempts.extend({**item, "symbol": symbol} for item in current_attempts)
            sources.add(source)
            if not isinstance(rows, list):
                raise ValueError("财务响应不是规范化清单")
            existing = service.store.list_records(dataset, symbol)
            known = {str(row["record_key"]): row for row in existing}
            incoming = []
            for raw in rows:
                if raw.get("schema_version") != "financial-v1" or raw.get("symbol") != symbol:
                    raise ValueError("财务数据契约或股票代码不匹配")
                period = str(raw.get("report_period") or "")
                if period and ((start and period < start.isoformat()) or period > end.isoformat()):
                    continue
                content = json.dumps(
                    raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
                )
                digest = hashlib.sha256(f"{dataset}|{source}|{content}".encode()).hexdigest()
                if digest in known:
                    unchanged += 1
                    continue
                publication = raw.get("published_at")
                revision = raw.get("source_updated_at")
                # 无可核实版本时间的数据只在采集后可见，不能按报告期倒填。
                available = (
                    max(datetime.fromisoformat(value) for value in (publication, revision) if value)
                    if publication and revision
                    else fetched
                )
                logical = (
                    period,
                    raw.get("statement_scope"),
                    raw.get("category"),
                    raw.get("item_name"),
                    raw.get("record_date"),
                )
                previous = [
                    row
                    for row in existing
                    if row.get("source") == source
                    and (
                        str(row.get("report_period") or ""),
                        row.get("statement_scope"),
                        row.get("category"),
                        row.get("item_name"),
                        row.get("record_date"),
                    )
                    == logical
                ]
                basis = "source_revision" if publication and revision else "observed"
                if previous and available <= max(
                    datetime.fromisoformat(str(row["available_at"])) for row in previous
                ):
                    available = max(available, fetched)
                    basis = "observed_revision"
                incoming.append(
                    {
                        **raw,
                        "record_key": digest,
                        "source": source,
                        "fetched_at": fetched.isoformat(),
                        "available_at": available.isoformat(),
                        "publication_time_known": bool(publication),
                        "availability_basis": basis,
                    }
                )
            # 单只股票的响应先完整校验；无效响应不能留下半张报表。
            service.store.upsert_records(dataset, incoming)
            saved += len(incoming)
        except Exception as error:
            if isinstance(error, AcquisitionFailed):
                failed_attempts = error.details.get("attempts", [])
                if isinstance(failed_attempts, list):
                    attempts.extend({**item, "symbol": symbol} for item in failed_attempts)
            failures.append(
                {"symbol": symbol, "message": "财务数据采集或保存失败，请查看来源尝试并重试"}
            )
    result = {
        "record_count": saved,
        "unchanged_count": unchanged,
        "attempts": attempts,
        "source_keys": sorted(sources),
        "failed_symbols": failures,
        "message": (
            f"{FINANCIAL_DATASETS[dataset]}：新增 {saved} 条版本，{unchanged} 条未变化；"
            "不按天复制财报。"
        ),
    }
    if failures:
        raise AcquisitionFailed("部分股票财务数据同步失败，已保留其他成功股票", result)
    return result
