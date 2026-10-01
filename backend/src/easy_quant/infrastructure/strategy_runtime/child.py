from __future__ import annotations

import contextlib
import io
import json
import sys
from collections.abc import Callable
from typing import cast


class RuntimeContext:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data

    def universe(self) -> list[str]:
        value = self.data.get("universe", [])
        return [str(item) for item in value] if isinstance(value, list) else []

    def factor(self, key: str, **parameters: object) -> object:
        symbol = str(parameters.get("symbol", ""))
        prices_value = self.data.get("prices", {})
        prices_by_symbol = prices_value if isinstance(prices_value, dict) else {}
        raw_prices = prices_by_symbol.get(symbol, [])
        prices = [float(item) for item in raw_prices] if isinstance(raw_prices, list) else []
        if key == "market.daily-bars":
            return [{"close": value} for value in prices]
        if key == "technical.ma":
            window = int(str(parameters.get("window", 5)))
            if len(prices) < window:
                return {"available": False, "required": window, "actual": len(prices)}
            return {"available": True, "value": sum(prices[-window:]) / window, "window": window}
        if key == "market.value":
            values = self.data.get("market_values", {})
            direct = values.get(symbol) if isinstance(values, dict) else None
            if direct is not None:
                return direct
            records = self.data.get("records", {})
            by_symbol = records.get("market-values", {}) if isinstance(records, dict) else {}
            history = by_symbol.get(symbol, []) if isinstance(by_symbol, dict) else []
            return history[-1] if isinstance(history, list) and history else None
        if key == "stat.expected-return":
            returns = [
                current / previous - 1
                for previous, current in zip(prices, prices[1:], strict=False)
            ]
            if not returns:
                return {"available": False, "expected_return": None, "win_rate": None}
            return {
                "available": True,
                "expected_return": sum(returns) / len(returns),
                "win_rate": sum(item > 0 for item in returns) / len(returns),
            }
        if key == "technical.rsi":
            window = int(str(parameters.get("window", 14)))
            if len(prices) <= window:
                return {"available": False, "required": window + 1, "actual": len(prices)}
            changes = [
                current - previous for previous, current in zip(prices, prices[1:], strict=False)
            ]
            recent = changes[-window:]
            gains = sum(max(value, 0) for value in recent) / window
            losses = sum(max(-value, 0) for value in recent) / window
            value = 100 if losses == 0 else 100 - 100 / (1 + gains / losses)
            return {"available": True, "value": value, "window": window}
        if key == "technical.macd":
            fast = int(str(parameters.get("fast", 12)))
            slow = int(str(parameters.get("slow", 26)))
            signal_window = int(str(parameters.get("signal", 9)))
            if len(prices) < slow + signal_window:
                return {
                    "available": False,
                    "required": slow + signal_window,
                    "actual": len(prices),
                }

            def ema(values: list[float], window: int) -> list[float]:
                multiplier = 2 / (window + 1)
                result = [values[0]]
                for value in values[1:]:
                    result.append((value - result[-1]) * multiplier + result[-1])
                return result

            fast_values, slow_values = ema(prices, fast), ema(prices, slow)
            differences = [
                left - right for left, right in zip(fast_values, slow_values, strict=True)
            ]
            signal_values = ema(differences, signal_window)
            return {
                "available": True,
                "dif": differences[-1],
                "dea": signal_values[-1],
                "histogram": (differences[-1] - signal_values[-1]) * 2,
            }
        if key in {"fundamental.latest", "fundamental.history"}:
            dataset = str(parameters.get("dataset", ""))
            values = self.data.get("records", {})
            by_dataset = values.get(dataset, {}) if isinstance(values, dict) else {}
            records = by_dataset.get(symbol, []) if isinstance(by_dataset, dict) else []
            if key == "fundamental.history":
                return records
            return records[-1] if isinstance(records, list) and records else None
        raise ValueError(f"未知因子: {key}")

    def current_price(self, symbol: str) -> float | None:
        values = self.data.get("current_prices", {})
        value = values.get(symbol) if isinstance(values, dict) else None
        return float(value) if value is not None else None

    def position(self, symbol: str) -> float:
        values = self.data.get("positions", {})
        value = values.get(symbol, 0) if isinstance(values, dict) else 0
        return float(value)


def main() -> None:
    request = json.loads(sys.stdin.read())
    namespace: dict[str, object] = {
        "__builtins__": {
            "abs": abs,
            "bool": bool,
            "dict": dict,
            "float": float,
            "int": int,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "print": print,
            "range": range,
            "str": str,
            "sum": sum,
        }
    }
    try:
        initialization_output = io.StringIO()
        with contextlib.redirect_stdout(initialization_output):
            exec(compile(request["source_code"], "<strategy>", "exec"), namespace)
        calls = request.get("calls")
        if isinstance(calls, list):
            results = [
                _execute_call(namespace, request.get("parameters", {}), item) for item in calls
            ]
            response = {"ok": True, "results": results}
        else:
            result = _execute_call(
                namespace,
                request.get("parameters", {}),
                {"context": request.get("context", {}), "phase": request.get("phase")},
            )
            result["stdout"] = initialization_output.getvalue() + str(result["stdout"])
            response = result
    except Exception as error:
        response = {
            "ok": False,
            "signals": [],
            "stdout": "",
            "error": f"{type(error).__name__}: {error}",
        }
    sys.stdout.write(json.dumps(response, ensure_ascii=False, default=str))


def _execute_call(
    namespace: dict[str, object], parameters: object, call: object
) -> dict[str, object]:
    output = io.StringIO()
    try:
        item = call if isinstance(call, dict) else {}
        phase = str(item.get("phase") or "before_market")
        candidate = namespace.get(phase)
        with contextlib.redirect_stdout(output):
            if candidate is None:
                signals = []
            else:
                function = cast(Callable[[RuntimeContext, dict[str, object]], object], candidate)
                raw_parameters = parameters if isinstance(parameters, dict) else {}
                raw_context = item.get("context", {})
                context = raw_context if isinstance(raw_context, dict) else {}
                signals = function(RuntimeContext(context), raw_parameters)
            if signals is None:
                signals = []
        return {"ok": True, "signals": signals, "stdout": output.getvalue()[:65536]}
    except Exception as error:
        return {
            "ok": False,
            "signals": [],
            "stdout": output.getvalue()[:65536],
            "error": f"{type(error).__name__}: {error}",
        }


if __name__ == "__main__":
    main()
