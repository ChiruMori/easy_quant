from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.domain.shared.errors import StateConflictError


class AcquisitionClient(Protocol):
    def acquire_with_attempts(
        self,
        request: SemanticRequest,
        *,
        force: bool = False,
        source_keys: set[str] | None = None,
    ) -> tuple[Any, list[Any]]: ...


def _identity(dataset_key: str, parameters: dict[str, object]) -> str:
    canonical = json.dumps(
        {"dataset_key": dataset_key, "parameters": parameters},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _exchange(symbol: str) -> str:
    if symbol.startswith(("4", "8", "92")):
        return "北京证券交易所"
    if symbol.startswith(("5", "6", "9")):
        return "上海证券交易所"
    return "深圳证券交易所"


def _rows(payload: bytes) -> object:
    return json.loads(payload.decode("utf-8"))


class MarketDataSyncService:
    """把真实来源的原始响应归一化写入平台仓储。"""

    def __init__(self, acquisitions: dict[str, AcquisitionClient], store: Any) -> None:
        self.acquisitions = acquisitions
        self.store = store

    def sync(
        self,
        dataset_key: str,
        *,
        symbols: list[str] | None = None,
        start_day: date | None = None,
        end_day: date | None = None,
        force: bool = False,
        source_keys: set[str] | None = None,
    ) -> dict[str, object]:
        if dataset_key == "securities":
            return self._sync_securities(force, source_keys, symbols)
        if dataset_key == "trading-calendar":
            return self._sync_calendar(start_day, end_day, force, source_keys)
        if dataset_key == "daily-bars":
            if not symbols or start_day is None or end_day is None:
                raise ValueError("同步日线需要股票、开始日期和结束日期")
            return self._sync_daily_bars(symbols, start_day, end_day, force, source_keys)
        if dataset_key in {"market-values", "pledge-ratios", "financial-indicators"}:
            if end_day is None:
                raise ValueError("同步基本面数据需要结束日期作为数据时点")
            if dataset_key == "financial-indicators" and not symbols:
                raise ValueError("同步财务指标需要指定股票")
            return self._sync_generic(
                dataset_key, symbols or [], start_day, end_day, force, source_keys
            )
        raise ValueError(f"不支持同步数据集 {dataset_key}")

    def quotes(self, symbols: list[str], *, force: bool = False) -> dict[str, str]:
        wanted = {str(symbol).zfill(6) for symbol in symbols}
        value, _, _, _ = self._acquire("live-quotes", {"market": "a-shares"}, force, None)
        if isinstance(value, dict):
            data = value.get("data")
            rows = list(data.get("diff", [])) if isinstance(data, dict) else []
        elif isinstance(value, list):
            rows = value
        else:
            rows = []
        result: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("f12") or row.get("代码") or row.get("code") or "").zfill(6)
            price = row.get("f2") or row.get("最新价") or row.get("price")
            if symbol in wanted and price not in (None, "-"):
                result[symbol] = str(Decimal(str(price)))
        missing = wanted - set(result)
        if missing:
            raise ValueError(f"实时价格缺失：{','.join(sorted(missing)[:20])}")
        return result

    def _acquire(
        self,
        dataset_key: str,
        parameters: dict[str, object],
        force: bool,
        source_keys: set[str] | None,
    ) -> tuple[object, list[dict[str, object]], str, datetime]:
        service = self.acquisitions[dataset_key]
        request = SemanticRequest(dataset_key, parameters, _identity(dataset_key, parameters))
        envelope, attempts = service.acquire_with_attempts(
            request, force=force, source_keys=source_keys
        )
        return (
            _rows(envelope.payload),
            [asdict(item) for item in attempts],
            envelope.source_key,
            envelope.fetched_at,
        )

    def _sync_securities(
        self, force: bool, source_keys: set[str] | None, symbols: list[str] | None
    ) -> dict[str, object]:
        value, attempts, source, _ = self._acquire("securities", {}, force, source_keys)
        raw_rows: list[dict[str, object]]
        if isinstance(value, list):
            raw_rows = value
        elif isinstance(value, dict):
            data = value.get("data")
            raw_rows = list(data.get("diff", [])) if isinstance(data, dict) else []
            if (
                isinstance(data, dict)
                and data.get("total") is not None
                and len(raw_rows) != int(data["total"])
            ):
                raise ValueError("证券清单不完整，已取消退市状态更新")
        else:
            raw_rows = []
        if not raw_rows and not symbols:
            raise ValueError("证券清单为空，已取消退市状态更新")
        instruments = []
        wanted = {str(symbol).zfill(6) for symbol in symbols or []}
        for row in raw_rows:
            symbol = str(row.get("code") or row.get("代码") or row.get("f12") or "").zfill(6)
            if len(symbol) != 6 or not symbol.isdigit():
                continue
            if wanted and symbol not in wanted:
                continue
            raw_listed_on = row.get("listed_on") or row.get("上市日期") or row.get("f26")
            listed_on = None
            if raw_listed_on and str(raw_listed_on) not in {"0", "-"}:
                text = str(raw_listed_on)[:10]
                if len(text) == 8 and text.isdigit():
                    text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
                try:
                    listed_on = date.fromisoformat(text).isoformat()
                except ValueError:
                    listed_on = None
            instruments.append(
                {
                    "symbol": symbol,
                    "name": str(row.get("name") or row.get("名称") or row.get("f14") or ""),
                    "exchange": _exchange(symbol),
                    "listed_on": listed_on,
                    "status": "delisted"
                    if str(row.get("status") or row.get("状态") or "").lower()
                    in {"delisted", "退市", "已退市"}
                    else "active",
                }
            )
        active_symbols = {str(item["symbol"]) for item in instruments if item["status"] == "active"}
        if not symbols and not active_symbols:
            raise ValueError("证券清单缺少在市股票，已取消退市状态更新")
        self.store.upsert_instruments(instruments)
        if not symbols:
            self.store.mark_missing_instruments_delisted(active_symbols)
        return {"record_count": len(instruments), "attempts": attempts, "source_key": source}

    def _sync_calendar(
        self,
        start_day: date | None,
        end_day: date | None,
        force: bool,
        source_keys: set[str] | None,
    ) -> dict[str, object]:
        value, attempts, source, _ = self._acquire("trading-calendar", {}, force, source_keys)
        days = []
        if isinstance(value, list):
            for row in value:
                if not isinstance(row, dict):
                    continue
                raw = row.get("trade_date") or row.get("交易日")
                if raw:
                    day = date.fromisoformat(str(raw)[:10])
                    if (start_day is None or day >= start_day) and (
                        end_day is None or day <= end_day
                    ):
                        days.append(day)
        self.store.upsert_trading_days(days)
        return {"record_count": len(days), "attempts": attempts, "source_key": source}

    def _sync_daily_bars(
        self,
        symbols: list[str],
        start_day: date,
        end_day: date,
        force: bool,
        source_keys: set[str] | None,
    ) -> dict[str, object]:
        normalized: list[dict[str, object]] = []
        all_attempts: list[dict[str, object]] = []
        sources: set[str] = set()
        incomplete: list[str] = []
        for input_symbol in symbols:
            symbol = str(input_symbol).zfill(6)
            adjustment = self.store.bar_adjustment(symbol) or "qfq"
            if adjustment not in {"none", "qfq"}:
                raise StateConflictError(
                    "历史日线复权口径不明确，无法自动补齐",
                    {"symbol": symbol, "adjustment": adjustment},
                )
            parameters: dict[str, object] = {
                "symbol": symbol,
                "start_date": start_day.isoformat(),
                "end_date": end_day.isoformat(),
                "adjustment": adjustment,
            }
            value, attempts, source, _ = self._acquire("daily-bars", parameters, force, source_keys)
            all_attempts.extend({**item, "symbol": symbol} for item in attempts)
            sources.add(source)
            bars = self._normalize_bars(symbol, value)
            normalized.extend({**row, "source": source, "adjustment": adjustment} for row in bars)
            latest = max((str(row["trading_day"]) for row in bars), default=None)
            if latest is None or latest < end_day.isoformat():
                incomplete.append(f"{symbol} 最新 {latest or '无'}")
        overwritten = self.store.upsert_bars(normalized)
        existing = {str(item["symbol"]) for item in self.store.list_instruments()}
        self.store.upsert_instruments(
            [
                {"symbol": symbol.zfill(6), "name": "", "exchange": _exchange(symbol.zfill(6))}
                for symbol in symbols
                if symbol.zfill(6) not in existing
            ]
        )
        return {
            "record_count": len(normalized),
            "overwritten": overwritten,
            "new_record_count": len(normalized) - overwritten,
            "attempts": all_attempts,
            "source_keys": sorted(sources),
            "message": (
                f"请求截至 {end_day.isoformat()}，来源返回的 K 线：{'、'.join(incomplete)}；"
                "其后暂无新交易数据，请核实停牌或来源延迟，系统不会补造行情。"
                if incomplete
                else ""
            ),
        }

    def _sync_generic(
        self,
        dataset_key: str,
        symbols: list[str],
        start_day: date | None,
        end_day: date,
        force: bool,
        source_keys: set[str] | None,
    ) -> dict[str, object]:
        requests: list[dict[str, object]]
        if dataset_key == "financial-indicators":
            requests = [
                {"symbol": str(symbol).zfill(6), "start_year": str((start_day or end_day).year)}
                for symbol in symbols
            ]
        elif dataset_key == "pledge-ratios":
            requests = [{"date": end_day.strftime("%Y%m%d")}]
        else:
            requests = [{"date": end_day.isoformat()}]
        wanted = {str(symbol).zfill(6) for symbol in symbols}
        normalized: list[dict[str, object]] = []
        attempts: list[dict[str, object]] = []
        sources: set[str] = set()
        for parameters in requests:
            value, current_attempts, source, fetched_at = self._acquire(
                dataset_key, parameters, force, source_keys
            )
            attempts.extend(current_attempts)
            sources.add(source)
            if isinstance(value, dict):
                data = value.get("data")
                raw_rows = list(data.get("diff", [])) if isinstance(data, dict) else []
            else:
                raw_rows = value if isinstance(value, list) else []
            request_symbol = str(parameters.get("symbol", ""))
            for index, row in enumerate(raw_rows):
                if not isinstance(row, dict):
                    continue
                symbol = str(
                    row.get("symbol")
                    or row.get("股票代码")
                    or row.get("代码")
                    or row.get("f12")
                    or request_symbol
                ).zfill(6)
                if wanted and symbol not in wanted:
                    continue
                raw_day = (
                    row.get("公告日期")
                    or row.get("发布日期")
                    or row.get("交易日期")
                    or row.get("日期")
                    or fetched_at.date()
                )
                if dataset_key == "market-values":
                    raw_day = fetched_at.date()
                available_day = date.fromisoformat(str(raw_day)[:10])
                if start_day and available_day < start_day:
                    continue
                if available_day > end_day:
                    continue
                serialized = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
                record_key = hashlib.sha256(
                    f"{symbol}|{available_day.isoformat()}|{index}|{serialized}".encode()
                ).hexdigest()
                mapped = dict(row)
                if dataset_key == "market-values":
                    mapped.update(
                        pe_ratio=row.get("f9"),
                        pb_ratio=row.get("f23"),
                        market_cap=row.get("f20"),
                        circulating_market_cap=row.get("f21"),
                    )
                normalized.append(
                    {
                        **mapped,
                        "symbol": symbol,
                        "record_key": record_key,
                        "available_at": f"{available_day.isoformat()}T23:59:59+08:00",
                    }
                )
        overwritten = self.store.upsert_records(dataset_key, normalized)
        return {
            "record_count": len(normalized),
            "overwritten": overwritten,
            "attempts": attempts,
            "source_keys": sorted(sources),
        }

    @staticmethod
    def _normalize_bars(symbol: str, value: object) -> list[dict[str, object]]:
        if isinstance(value, dict):
            data = value.get("data")
            klines = data.get("klines", []) if isinstance(data, dict) else []
            rows = []
            for item in klines if isinstance(klines, list) else []:
                parts = str(item).split(",")
                if len(parts) >= 6:
                    rows.append(
                        {
                            "symbol": symbol,
                            "trading_day": parts[0],
                            "open": parts[1],
                            "close": parts[2],
                            "high": parts[3],
                            "low": parts[4],
                            "volume": parts[5],
                        }
                    )
        elif isinstance(value, list):
            rows = [
                {
                    "symbol": symbol,
                    "trading_day": row.get("日期") or row.get("date"),
                    "open": row.get("开盘") or row.get("open"),
                    "close": row.get("收盘") or row.get("close"),
                    "high": row.get("最高") or row.get("high"),
                    "low": row.get("最低") or row.get("low"),
                    "volume": row.get("成交量") or row.get("volume"),
                }
                for row in value
                if isinstance(row, dict)
            ]
        else:
            rows = []
        result = []
        for row in rows:
            if not row["trading_day"]:
                continue
            day = date.fromisoformat(str(row["trading_day"])[:10])
            result.append(
                {
                    **row,
                    "trading_day": day.isoformat(),
                    "available_at": f"{day.isoformat()}T15:00:00+08:00",
                    **{
                        key: str(Decimal(str(row[key])))
                        for key in ("open", "high", "low", "close", "volume")
                    },
                }
            )
        return result
