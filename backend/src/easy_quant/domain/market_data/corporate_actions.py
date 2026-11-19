"""公司行为契约与定点复权。原始成交事实不变；完整性与可获知时间独立校验。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from easy_quant.domain.market_data.indices import is_index
from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.shared.value_objects import ensure_utc

DATASET = "corporate-actions"
POLICY = "corporate-actions-v1"
KINDS = {"cash_dividend", "bonus", "capitalization", "rights", "split", "consolidation"}
ZONE = ZoneInfo("Asia/Shanghai")


def day(value: object) -> date:
    return value if type(value) is date else date.fromisoformat(str(value))


def instant(value: object) -> datetime:
    return ensure_utc(value if isinstance(value, datetime) else datetime.fromisoformat(str(value)))


def number(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("公司行为数值必须有限")
    return result


@dataclass(frozen=True)
class CorporateAction:
    event_id: str
    symbol: str
    ex_date: date
    record_date: date
    available_at: datetime
    cash_per_share: Decimal
    share_multiplier: Decimal
    rights_ratio: Decimal
    rights_price: Decimal
    previous_close: Decimal
    cash_pay_date: date | None
    shares_listing_date: date | None
    reference_price: Decimal | None
    record_key: str
    kinds: tuple[str, ...]

    @classmethod
    def parse(cls, row: Mapping[str, Any]) -> CorporateAction:
        action = cls(
            str(row["event_id"]),
            str(row["symbol"]),
            day(row["ex_date"]),
            day(row["record_date"]),
            instant(row["available_at"]),
            number(row["cash_per_share"]),
            number(row["share_multiplier"]),
            number(row["rights_ratio"]),
            number(row["rights_price"]),
            number(row["previous_close"]),
            day(row["cash_pay_date"]) if row.get("cash_pay_date") else None,
            day(row["shares_listing_date"]) if row.get("shares_listing_date") else None,
            number(row["reference_price"]) if row.get("reference_price") is not None else None,
            str(row.get("record_key", "")),
            tuple(row["kinds"]),
        )
        if (
            not action.event_id
            or is_index(action.symbol)
            or action.record_date >= action.ex_date
            or not action.kinds
            or not set(action.kinds) <= KINDS
            or action.share_multiplier <= 0
            or action.previous_close <= 0
            or min(action.cash_per_share, action.rights_ratio, action.rights_price) < 0
            or (action.rights_ratio > 0 and action.rights_price <= 0)
            or (action.cash_per_share > 0 and action.cash_pay_date is None)
            or (action.share_multiplier != 1 and action.shares_listing_date is None)
            or (action.cash_per_share > 0 and "cash_dividend" not in action.kinds)
            or (action.rights_ratio > 0 and "rights" not in action.kinds)
            or (
                action.share_multiplier > 1
                and not set(action.kinds) & {"bonus", "capitalization", "split"}
            )
            or (action.share_multiplier < 1 and "consolidation" not in action.kinds)
            or any(
                d is not None and d < action.ex_date
                for d in (action.cash_pay_date, action.shares_listing_date)
            )
            or action.ex_reference <= 0
        ):
            raise ValueError("公司行为日期、单位、类型或参考价格无效/不完整")
        return action

    @property
    def ex_reference(self) -> Decimal:
        if self.reference_price is not None:
            return self.reference_price
        return (
            self.previous_close - self.cash_per_share + self.rights_ratio * self.rights_price
        ) / (self.share_multiplier + self.rights_ratio)

    @property
    def price_ratio(self) -> Decimal:
        return self.ex_reference / self.previous_close


class CorporateActionBook:
    def __init__(self, records: Iterable[Mapping[str, Any]]) -> None:
        self.records = tuple(records)
        self.by_symbol: dict[str, list[Mapping[str, Any]]] = {}
        for row in self.records:
            self.by_symbol.setdefault(str(row.get("symbol", "")), []).append(row)

    def events(self, symbol: str, as_of: datetime) -> tuple[CorporateAction, ...]:
        as_of = instant(as_of)
        versions: dict[str, Mapping[str, Any]] = {}
        for row in self.by_symbol.get(symbol, []):
            if row.get("record_kind") != "event" or instant(row["available_at"]) > as_of:
                continue
            key = str(row["event_id"])
            previous = versions.get(key)
            if previous is None or instant(previous["available_at"]) < instant(row["available_at"]):
                versions[key] = row
            elif instant(previous["available_at"]) == instant(row["available_at"]) and (
                previous.get("record_key") != row.get("record_key")
            ):
                raise StateConflictError("同一公司行为存在同时间冲突版本", {"symbol": symbol})
        events = [
            CorporateAction.parse(row)
            for row in versions.values()
            if row.get("status") != "cancelled"
        ]
        events.sort(key=lambda event: (event.ex_date, event.event_id))
        if len({event.ex_date for event in events}) != len(events):
            raise StateConflictError("同日公司行为必须合并为一个除权事件", {"symbol": symbol})
        return tuple(events)

    def require_coverage(self, symbol: str, start: date, end: date, as_of: datetime) -> None:
        as_of = instant(as_of)
        if is_index(symbol) or start > end:
            return
        intervals = sorted(
            (day(row["start_day"]), day(row["end_day"]))
            for row in self.by_symbol.get(symbol, [])
            if row.get("record_kind") == "coverage" and row.get("complete") is True
        )
        cursor = start.toordinal()
        for left, right in intervals:
            if left.toordinal() > cursor:
                break
            cursor = max(cursor, right.toordinal() + 1)
        if cursor <= end.toordinal():
            raise StateConflictError(
                "公司行为数据覆盖未核实，已阻止使用未经复权验证的行情",
                {
                    "symbol": symbol,
                    "start_day": str(start),
                    "end_day": str(end),
                    "missing_from": str(date.fromordinal(cursor)),
                    "dataset": DATASET,
                },
            )
        # 完整性证明不能掩盖事后才采集/修订的历史经济信息。
        visible = {
            str(row["event_id"])
            for row in self.by_symbol.get(symbol, [])
            if row.get("record_kind") == "event" and instant(row["available_at"]) <= as_of
        }
        for row in self.by_symbol.get(symbol, []):
            if row.get("record_kind") != "event":
                continue
            if (
                start <= day(row["ex_date"]) <= min(end, as_of.astimezone(ZONE).date())
                and str(row["event_id"]) not in visible
                and row.get("status") != "cancelled"
            ):
                raise StateConflictError(
                    "已生效公司行为缺少当时可获知的版本",
                    {"symbol": symbol, "event_id": row["event_id"]},
                )
        attestations = [
            row for row in self.by_symbol.get(symbol, []) if row.get("record_kind") == "coverage"
        ]
        for event in self.events(symbol, as_of):
            if start <= event.ex_date <= end and not any(
                day(proof["start_day"]) <= event.ex_date <= day(proof["end_day"])
                and event.record_key in proof.get("event_keys", [])
                for proof in attestations
            ):
                raise StateConflictError(
                    "公司行为版本尚未纳入覆盖核验", {"event_id": event.event_id}
                )
        for row in self.by_symbol.get(symbol, []):
            if row.get("record_kind") != "candidate" or row.get("price_event_candidate") is False:
                continue
            if start <= day(row["ex_date"]) <= end and not any(
                day(proof["start_day"]) <= day(row["ex_date"]) <= day(proof["end_day"])
                and row["record_key"] in proof.get("resolved_candidate_keys", [])
                for proof in attestations
            ):
                raise StateConflictError(
                    "发现尚未核对的公司行为候选，覆盖证明需要更新",
                    {"symbol": symbol, "candidate_key": row["record_key"]},
                )

    def adjust(
        self,
        rows: Iterable[Mapping[str, Any]],
        symbol: str,
        as_of: datetime,
        *,
        mode: str = "qfq",
        anchor: date | None = None,
    ) -> list[dict[str, Any]]:
        as_of = instant(as_of)
        if mode not in {"raw", "qfq", "hfq"}:
            raise ValueError("复权方式必须为 raw、qfq 或 hfq")
        anchor = anchor or as_of.astimezone(ZONE).date()
        if anchor > as_of.astimezone(ZONE).date():
            raise ValueError("复权锚点不能晚于决策时点")
        bars = sorted(
            (
                dict(row)
                for row in rows
                if day(row["trading_day"]) <= anchor and instant(row["available_at"]) <= as_of
            ),
            key=lambda row: str(row["trading_day"]),
        )
        if not bars:
            return []
        if any(row.get("adjustment") != "none" or not row.get("source") for row in bars):
            raise StateConflictError(
                "研究与成交必须使用有来源的不复权原价；禁止反推旧复权价", {"symbol": symbol}
            )
        if is_index(symbol):
            return [{**row, "price_basis": "raw-index"} for row in bars]
        start = day(bars[0]["trading_day"])
        self.require_coverage(symbol, start, anchor, as_of)
        events = [event for event in self.events(symbol, as_of) if start < event.ex_date <= anchor]
        for event in events:
            preceding = [row for row in bars if day(row["trading_day"]) < event.ex_date]
            if preceding and abs(number(preceding[-1]["close"]) - event.previous_close) > Decimal(
                "0.005"
            ):
                raise StateConflictError(
                    "事件前收盘价与原始行情不符，请核对单位及来源", {"event_id": event.event_id}
                )
        for row in bars:
            trading_day = day(row["trading_day"])
            price_scale = Decimal(1)
            share_scale = Decimal(1)
            for event in events:
                relevant = (
                    trading_day < event.ex_date if mode != "hfq" else trading_day >= event.ex_date
                )
                if relevant:
                    price_scale *= event.price_ratio if mode != "hfq" else 1 / event.price_ratio
                    # 股数换算与现金红利造成的价格调整严格分开；不虚构历史成交量。
                    share_scale *= event.share_multiplier + event.rights_ratio
            row.update(
                price_basis=mode,
                adjustment_anchor=str(start if mode == "hfq" else anchor),
                share_scale=float(share_scale),
            )
            for name in ("open", "high", "low", "close"):
                if row.get(name) is not None:
                    row[f"raw_{name}"] = row[name]
                    if mode != "raw":
                        row[name] = float(number(row[name]) * price_scale)
            row["price_scale"] = 1.0 if mode == "raw" else float(price_scale)
            if row.get("volume") is not None:
                volume = number(row["volume"])
                row["adjusted_volume"] = float(
                    volume * share_scale
                    if mode == "qfq"
                    else volume / share_scale
                    if mode == "hfq"
                    else volume
                )
                if row.get("amount") is not None and volume > 0:
                    row["adjusted_vwap"] = float(
                        number(row["amount"]) / volume * number(row["price_scale"])
                    )
        return bars
