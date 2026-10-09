from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any

from easy_quant.factors.context import FactorContext
from easy_quant.factors.registry import build_default_registry

REGISTRY = build_default_registry()
MAX_STATE_BYTES = 256 * 1024


def decimal_value(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("数值必须有限")
    return result


class SnapshotGateway:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def records(self, dataset: str, symbol: str) -> Iterable[Mapping[str, object]]:
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
        for row in rows:
            item = dict(row)
            for name in (
                "open",
                "high",
                "low",
                "close",
                "volume",
                "pe_ratio",
                "pb_ratio",
                "market_cap",
                "circulating_market_cap",
                "roe",
                "net_profit",
                "adjusted_net_profit",
                "pledge_ratio",
            ):
                if item.get(name) not in (None, "", "-"):
                    item[name] = decimal_value(item[name])
            raw = item.get("available_at", cutoff)
            item["available_at"] = (
                raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
            )
            normalized.append(item)
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
        self.data = data
        self.store = StrategyStore(state if state is not None else {})
        self._quote_provider = quote_provider
        self._quotes: dict[str, Decimal] = {}
        self.mock_usage: list[dict[str, object]] = []
        self._reserved_cash = Decimal(0)
        self._reserved_positions: dict[str, Decimal] = {}

    def universe(self) -> list[str]:
        symbols = set(self.data.get("universe", []))
        # 证券快照补入尚无日线的新上市标的；只采用决策时点已知的状态。
        for symbol in self.data.get("records", {}).get("security-status", {}):
            status = self.factor("fundamental.latest", symbol=symbol, dataset="security-status")
            if not status or status.get("status") in {"delisted", "suspended"}:
                continue
            listed_on = status.get("listed_on")
            if listed_on and str(listed_on) > str(self.data.get("trading_day", "9999-12-31")):
                continue
            symbols.add(symbol)
        return sorted(symbols)

    def securities(self, industry: str | None = None) -> list[str]:
        if industry is None:
            return self.universe()
        return [
            symbol
            for symbol in self.universe()
            if (self.security_info(symbol) or {}).get("industry_code") == industry
        ]

    def security_info(self, symbol: str) -> dict[str, object] | None:
        value = self.factor("fundamental.latest", symbol=symbol, dataset="security-status")
        industry = self.factor(
            "fundamental.latest", symbol=symbol, dataset="sw-industry-memberships"
        )
        if value is None and industry is None:
            return None
        return {**(value or {}), **(industry or {})}

    def financials(self, symbol: str) -> object:
        return self.factor("fundamental.history", symbol=symbol, dataset="financial-indicators")

    def valuation(self, symbol: str) -> object:
        return self.factor("market.value", symbol=symbol)

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
            prices = list(data.get("prices", {}).get(symbol, []))
            if prices and len(prices) < required:
                self.mock_usage.append(
                    {"factor": key, "symbol": symbol, "count": required - len(prices)}
                )
                data = {
                    **data,
                    "prices": {
                        **data["prices"],
                        symbol: [prices[0]] * (required - len(prices)) + prices,
                    },
                }
        as_of = datetime.fromisoformat(data.get("decision_at", "9999-12-31T00:00:00+00:00"))
        return REGISTRY.call(key, FactorContext(SnapshotGateway(data), as_of), parameters)

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
        return {
            "cash": decimal_value(self.data.get("cash") or 0),
            "positions": {
                key: decimal_value(value) for key, value in self.data.get("positions", {}).items()
            },
            "costs": {
                key: decimal_value(value) for key, value in self.data.get("costs", {}).items()
            },
        }

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
    ) -> dict[str, object]:
        fraction = decimal_value(ratio)
        if (
            not 0 < fraction <= 1
            or action not in {"buy", "sell"}
            or type(lot_size) is not int
            or lot_size <= 0
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
            amount = basis * fraction / unit_cost
        else:
            amount = basis * fraction
        quantity = (amount / lot_size).to_integral_value(rounding=ROUND_DOWN) * lot_size
        # 整体卖出允许清理不足一手的剩余持仓；部分卖出保持交易单位。
        if action == "sell" and fraction == 1:
            quantity = basis
        if action == "buy":
            estimated = quantity * unit_cost
            if self._reserved_cash + estimated > basis:
                quantity = Decimal(0)
            self._reserved_cash += quantity * unit_cost
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
