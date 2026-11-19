from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from time import perf_counter_ns
from typing import Any

from easy_quant.domain.market_data.fundamentals import FIELD_METADATA
from easy_quant.domain.market_data.indices import is_index
from easy_quant.factors.context import FactorContext
from easy_quant.factors.registry import build_default_registry
from easy_quant.platform_library.catalog import build_library_registry

REGISTRY = build_default_registry()
LIBRARY_REGISTRY = build_library_registry()
MAX_STATE_BYTES = 256 * 1024


def decimal_value(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("数值必须有限")
    return result


class SnapshotGateway:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        from easy_quant.domain.market_data.corporate_actions import CorporateActionBook

        self._corporate_book = CorporateActionBook(data.get("corporate_actions", []))

    def records(self, dataset: str, symbol: str) -> Iterable[Mapping[str, object]]:
        if dataset in {"daily-bars", "raw-daily-bars", "hfq-daily-bars"} and self.data.get(
            "price_policy"
        ):
            cutoff = datetime.fromisoformat(self.data["decision_at"])
            mode = {"daily-bars": "qfq", "raw-daily-bars": "raw", "hfq-daily-bars": "hfq"}[dataset]
            adjusted = self._corporate_book.adjust(
                self.data.get("bars", {}).get(symbol, []), symbol, cutoff, mode=mode
            )
            data = {**self.data, "bars": {symbol: adjusted}}
            data.pop("price_policy")
            # 已经使用当前实例的索引校验和复权，归一化时无需重建全市场事件索引。
            data.pop("corporate_actions", None)
            return SnapshotGateway(data).records("daily-bars", symbol)
        cutoff = self.data.get("decision_at", "9999-12-31T00:00:00+00:00")
        if dataset == "daily-bars":
            rows = self.data.get("bars", {}).get(symbol)
            if rows is None:
                rows = [
                    {"close": decimal_value(value), "available_at": cutoff}
                    for value in self.data.get("prices", {}).get(symbol, [])
                ]
        else:
            rows = self.data.get("records", {}).get(dataset, {}).get(symbol, [])
            if dataset == "market-values" and self.data.get("market_values", {}).get(symbol):
                rows = [self.data["market_values"][symbol]]
        normalized = []
        boundary = datetime.fromisoformat(str(cutoff))
        for row in rows:
            raw_at = row.get("available_at", cutoff)
            at = raw_at if isinstance(raw_at, datetime) else datetime.fromisoformat(str(raw_at))
            if at > boundary:
                continue
            from easy_quant.infrastructure.data_sources.financial_normalization import (
                project_legacy_revenue,
            )

            item = project_legacy_revenue(row) if dataset == "income-statements" else dict(row)
            for name in (
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "raw_open",
                "raw_high",
                "raw_low",
                "raw_close",
                "adjusted_volume",
                "adjusted_vwap",
                "pe_ratio",
                "pb_ratio",
                "market_cap",
                "circulating_market_cap",
                "roe",
                "net_profit",
                "adjusted_net_profit",
                "pledge_ratio",
                *FIELD_METADATA,
            ):
                if item.get(name) not in (None, "", "-"):
                    item[name] = float(str(item[name]))
            raw = item.get("available_at", cutoff)
            item["available_at"] = (
                raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
            )
            normalized.append(item)
        if dataset == "daily-bars":
            return sorted(
                normalized, key=lambda row: (str(row.get("trading_day", "")), row["available_at"])
            )
        return sorted(
            normalized,
            key=lambda row: (row["available_at"], str(row.get("report_period", ""))),
        )


class StrategyStore:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def get(self, key: str, default: object = None) -> Any:
        return deepcopy(self._values.get(str(key), default))

    def set(self, key: str, value: object) -> None:
        if not isinstance(key, str) or not key or len(key) > 128:
            raise ValueError("状态键必须为 1–128 字符")
        candidate = {**self._values, key: value}
        encoded = json.dumps(candidate, ensure_ascii=True, default=_state_default, allow_nan=False)
        if len(encoded.encode()) > MAX_STATE_BYTES:
            raise ValueError("策略状态超过 256 KiB")
        self._values[key] = json.loads(encoded)[key]

    def delete(self, key: str) -> None:
        self._values.pop(str(key), None)


def _state_default(value: object) -> str:
    if isinstance(value, Decimal) and value.is_finite():
        return str(value)
    raise TypeError("状态只支持 JSON 值与有限 Decimal（以字符串保存）")


class RuntimeContext:
    def __init__(
        self,
        data: dict[str, Any],
        *,
        state: dict[str, Any] | None = None,
        quote_provider: Callable[[list[str]], dict[str, object]] | None = None,
    ) -> None:
        # 完整性审计包含晚到/未来修订，不能直接暴露给策略代码。
        self.data = {key: value for key, value in data.items() if key != "corporate_actions"}
        self.store = StrategyStore(state if state is not None else {})
        self._quote_provider = quote_provider
        self._quotes: dict[str, Decimal] = {}
        self.factor_metrics: dict[str, dict[str, int]] = {}
        self.mock_usage: list[dict[str, object]] = []
        self._reserved_cash = decimal_value(data.get("reserved_cash", 0))
        self._reserved_positions = {
            key: decimal_value(value) for key, value in data.get("reserved_positions", {}).items()
        }
        for symbol, value in data.get("locked_shares", {}).items():
            self._reserved_positions[symbol] = self._reserved_positions.get(
                symbol, Decimal(0)
            ) + decimal_value(value)
        as_of = datetime.fromisoformat(data.get("decision_at", "9999-12-31T00:00:00+00:00"))
        self._factor_context = FactorContext(SnapshotGateway(data), as_of)
        self._buy_symbols = set(data.get("pending_buy_symbols", []))

    def universe(self) -> list[str]:
        symbols = set(self.data.get("universe", []))
        # 证券快照补入尚无日线的新上市标的；只采用决策时点已知的状态。
        for symbol in self.data.get("records", {}).get("security-status", {}):
            status = self.library("fundamental.latest", symbol=symbol, dataset="security-status")
            if not status or status.get("status") in {"delisted", "suspended"}:
                continue
            listed_on = status.get("listed_on")
            if listed_on and str(listed_on) > str(self.data.get("trading_day", "9999-12-31")):
                continue
            symbols.add(symbol)
        return sorted(symbol for symbol in symbols if not is_index(symbol))

    def securities(self, industry: str | None = None) -> list[str]:
        if industry is None:
            return self.universe()
        return [
            symbol
            for symbol in self.universe()
            if (self.security_info(symbol) or {}).get("industry_code") == industry
        ]

    def security_info(self, symbol: str) -> dict[str, object] | None:
        value = self.library("fundamental.latest", symbol=symbol, dataset="security-status")
        industry = self.library(
            "fundamental.latest", symbol=symbol, dataset="sw-industry-memberships"
        )
        if value is None and industry is None:
            return None
        return {**(value or {}), **(industry or {})}

    def history(self, symbol: str, dataset: str = "daily-bars", *, adjustment: str = "qfq"):
        if dataset == "daily-bars":
            if adjustment not in {"raw", "qfq", "hfq"}:
                raise ValueError("复权方式必须为 raw、qfq 或 hfq")
            dataset = {"raw": "raw-daily-bars", "qfq": "daily-bars", "hfq": "hfq-daily-bars"}[
                adjustment
            ]
        return self._factor_context.frame(dataset, symbol)

    def corporate_actions(self, symbol: str) -> list[dict[str, object]]:
        from easy_quant.domain.market_data.corporate_actions import ZONE

        cutoff = self._factor_context.as_of
        gateway = self._factor_context.gateway
        assert isinstance(gateway, SnapshotGateway)
        return [
            {
                "event_id": event.event_id,
                "record_key": event.record_key,
                "ex_date": str(event.ex_date),
                "price_ratio": float(event.price_ratio),
                "share_multiplier": float(event.share_multiplier),
                "cash_per_share": float(event.cash_per_share),
            }
            for event in gateway._corporate_book.events(symbol, cutoff)
            if event.ex_date <= cutoff.astimezone(ZONE).date()
        ]

    def trading_day(self) -> str:
        from easy_quant.domain.market_data.corporate_actions import ZONE

        return str(
            self.data.get("trading_day") or self._factor_context.as_of.astimezone(ZONE).date()
        )

    def financials(self, symbol: str):
        from easy_quant.platform_library.frames import research_frame

        return research_frame(
            self.library("fundamental.history", symbol=symbol, dataset="financial-indicators"),
            FIELD_METADATA,
        )

    def valuation(self, symbol: str) -> object:
        return self.library("market.value", symbol=symbol)

    def library(self, key: str, **parameters: object) -> Any:
        return LIBRARY_REGISTRY.call(key, self._factor_context, parameters)

    def factor(self, key: str, **parameters: object) -> Any:
        data = self.data
        # Mock 仅在显式快测模式补技术因子的窗口，绝不补造财务指标。
        if (
            data.get("runtime") == "quick_test"
            and data.get("allow_mock")
            and key.startswith("technical.")
        ):
            symbol = str(parameters.get("symbol", ""))
            required = (
                int(str(parameters.get("slow", 26))) + int(str(parameters.get("signal", 9)))
                if key == "technical.macd"
                else int(str(parameters.get("window", 14 if key == "technical.rsi" else 5)))
                + (1 if key == "technical.rsi" else 0)
            )
            if not 1 <= required <= 2500:
                raise ValueError("窗口必须在 1–2500 之间")
            prices = [str(row["close"]) for row in self._factor_context.read("daily-bars", symbol)]
            if prices and len(prices) < required:
                self.mock_usage.append(
                    {"factor": key, "symbol": symbol, "count": required - len(prices)}
                )
                data = {
                    **data,
                    "bars": {s: rows for s, rows in data.get("bars", {}).items() if s != symbol},
                    "prices": {
                        **data["prices"],
                        symbol: [prices[0]] * (required - len(prices)) + prices,
                    },
                }
                data.pop("price_policy", None)
        as_of = datetime.fromisoformat(data.get("decision_at", "9999-12-31T00:00:00+00:00"))
        context = (
            self._factor_context
            if data is self.data
            else FactorContext(SnapshotGateway(data), as_of)
        )
        REGISTRY.get(key)
        started = perf_counter_ns()
        try:
            return REGISTRY.call(key, context, parameters)
        finally:
            metric = self.factor_metrics.setdefault(key, {"calls": 0, "elapsed_ns": 0})
            metric["calls"] += 1
            metric["elapsed_ns"] += perf_counter_ns() - started

    def quotes(self, symbols: list[str]) -> dict[str, Decimal]:
        wanted = sorted(set(str(symbol) for symbol in symbols))
        if len(wanted) > 10000:
            raise ValueError("单次报价请求最多 10000 个标的")
        missing = [symbol for symbol in wanted if symbol not in self._quotes]
        if missing:
            if self.data.get("phase") != "on_market":
                raise ValueError("临时报价仅在盘中阶段可用")
            raw = (
                self._quote_provider(missing)
                if self._quote_provider is not None
                else self.data.get("current_prices", {})
            )
            for symbol in missing:
                if raw.get(symbol) is not None:
                    value = decimal_value(raw[symbol])
                    if value <= 0:
                        raise ValueError(f"报价无效：{symbol}")
                    self._quotes[symbol] = value
        return {symbol: self._quotes[symbol] for symbol in wanted if symbol in self._quotes}

    def current_price(self, symbol: str) -> Decimal | None:
        return self.quotes([symbol]).get(symbol)

    def position(self, symbol: str) -> Decimal:
        return decimal_value(self.data.get("positions", {}).get(symbol, 0))

    def portfolio(self) -> dict[str, object]:
        result = {
            "cash": decimal_value(self.data.get("cash") or 0),
            "available_cash": max(
                Decimal(0), decimal_value(self.data.get("cash") or 0) - self._reserved_cash
            ),
            "reserved_cash": self._reserved_cash,
            "reserved_positions": dict(self._reserved_positions),
            "pending_buy_symbols": sorted(self._buy_symbols),
            "positions": {
                key: decimal_value(value) for key, value in self.data.get("positions", {}).items()
            },
            "costs": {
                key: decimal_value(value) for key, value in self.data.get("costs", {}).items()
            },
        }
        if decimal_value(self.data.get("receivable_cash", 0)) or self.data.get("locked_shares"):
            result["receivable_cash"] = decimal_value(self.data.get("receivable_cash", 0))
            result["locked_shares"] = {
                key: decimal_value(value)
                for key, value in self.data.get("locked_shares", {}).items()
            }
        return result

    def signal(
        self,
        symbol: str,
        action: str,
        ratio: object,
        reason: str,
        *,
        price: object | None = None,
        lot_size: int = 100,
        trigger_price: object | None = None,
        trigger_operator: str | None = None,
        expected_holdings: int = 10,
    ) -> dict[str, object]:
        fraction = decimal_value(ratio)
        if (
            not 0 < fraction <= 1
            or action not in {"buy", "sell"}
            or type(lot_size) is not int
            or lot_size <= 0
            or type(expected_holdings) is not int
            or expected_holdings <= 0
        ):
            raise ValueError("动作、比例或交易单位无效")
        basis = (
            decimal_value(self.data.get("cash") or 0) if action == "buy" else self.position(symbol)
        )
        unit_cost = Decimal(0)
        reference_price = decimal_value(price) if price is not None else None
        if action == "buy":
            raw_price = price if price is not None else self.current_price(symbol)
            if raw_price is None or decimal_value(raw_price) <= 0:
                raise ValueError("买入比例必须提供有效参考价格")
            fee_rate = decimal_value(self.data.get("fee_rate", "0.0003"))
            slippage = decimal_value(self.data.get("slippage_rate", 0))
            unit_cost = decimal_value(raw_price) * (1 + slippage) * (1 + fee_rate)
            reference_price = decimal_value(raw_price)
            # 单标的预算固定于调用开始，预留只减少可用额，不缩小预算。
            equity = decimal_value(self.data.get("cash") or 0)
            equity += decimal_value(self.data.get("receivable_cash", 0))
            for held, held_quantity in self.data.get("positions", {}).items():
                history = self.data.get("prices", {}).get(held, [])
                mark = (
                    (reference_price if held == symbol else None)
                    or self.data.get("current_prices", {}).get(held)
                    or (history[-1] if history else self.data.get("costs", {}).get(held, 0))
                )
                equity += decimal_value(held_quantity) * decimal_value(mark)
            basis = equity / expected_holdings
            held_value = self.position(symbol) * reference_price
            # 同标的已预留买入时不重复建议，避免跨轮叠加。
            occupied = {
                key
                for key, value in self.data.get("positions", {}).items()
                if decimal_value(value) > 0
            } | self._buy_symbols
            allowed = symbol not in self._buy_symbols and (
                symbol in occupied or len(occupied) < expected_holdings
            )
            budget = (
                max(Decimal(0), min(basis * fraction, basis - held_value))
                if allowed
                else Decimal(0)
            )
            available = max(
                Decimal(0), decimal_value(self.data.get("cash") or 0) - self._reserved_cash
            )
            amount = min(budget, available) / unit_cost
        else:
            amount = basis * fraction
        quantity = (amount / lot_size).to_integral_value(rounding=ROUND_DOWN) * lot_size
        # 整体卖出允许清理不足一手的剩余持仓；部分卖出保持交易单位。
        if action == "sell" and fraction == 1:
            quantity = basis
        if action == "buy":
            self._reserved_cash += quantity * unit_cost
            if quantity > 0:
                self._buy_symbols.add(symbol)
        else:
            reserved = self._reserved_positions.get(symbol, Decimal(0))
            if reserved + quantity > basis:
                quantity = Decimal(0)
            self._reserved_positions[symbol] = reserved + quantity
        return {
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "reason": reason,
            "ratio": fraction,
            "ratio_basis": basis,
            "reference_price": reference_price,
            "trigger_price": trigger_price,
            "trigger_operator": trigger_operator,
        }
