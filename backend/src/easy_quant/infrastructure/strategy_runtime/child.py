from __future__ import annotations

import contextlib
import io
import json
import sys
from bisect import bisect_left
from collections.abc import Callable
from copy import deepcopy
from decimal import Decimal

# -I 不读取工作目录/PYTHONPATH；只添加随应用发布的固定 src 路径。
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from easy_quant.strategy_api.context import RuntimeContext


def _request_quotes(symbols):
    _stream_reply({"quote_request": symbols})
    response = json.loads(sys.stdin.readline())
    if response.get("error"):
        raise ValueError(response["error"])
    return response.get("quotes", {})


def main() -> None:
    request = json.loads(sys.stdin.readline())
    namespace: dict[str, object] = {"__builtins__": _safe_builtins()}
    try:
        initialization_output = io.StringIO()
        with contextlib.redirect_stdout(initialization_output):
            exec(compile(request["source_code"], "<strategy>", "exec"), namespace)
        calls = request.get("calls")
        if isinstance(calls, list):
            results = []
            state = deepcopy(calls[0].get("context", {}).get("strategy_state", {})) if calls else {}
            for item in calls:
                item["context"]["strategy_state"] = state
                result = _execute_call(namespace, request.get("parameters", {}), item)
                if result.get("ok"):
                    state = result["state"]
                results.append(result)
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
    sys.stdout.write(json.dumps(response, ensure_ascii=True, default=str))


def stream_main() -> None:
    """回测专用行协议；一次子进程只服务一个策略版本。"""
    try:
        initialization = json.loads(sys.stdin.readline())
        compiled = compile(initialization["source_code"], "<strategy>", "exec")
        parameters = initialization.get("parameters", {})
        _stream_reply({"ok": True, "ready": True})
    except Exception as error:
        _stream_reply({"ok": False, "error": f"{type(error).__name__}: {error}"})
        return

    price_days: dict[str, list[str]] = {}
    prices: dict[str, list[str]] = {}
    strategy_state: dict[str, object] = {}

    def add_prices(rows: list[dict[str, object]]) -> None:
        for row in rows:
            symbol, day = str(row["symbol"]), str(row["trading_day"])
            days = price_days.setdefault(symbol, [])
            values = prices.setdefault(symbol, [])
            position = bisect_left(days, day)
            if position < len(days) and days[position] == day:
                values[position] = str(row["close"])
            else:
                days.insert(position, day)
                values.insert(position, str(row["close"]))

    namespace: dict[str, object] = {}
    active_day: str | None = None
    phase_index = 3
    phases = ("before_market", "on_market", "after_market")

    def execute_phase(request: dict[str, object], phase: str) -> dict[str, object]:
        nonlocal namespace, active_day, phase_index, strategy_state
        trading_day = str(request["trading_day"])
        if phase == "before_market":
            if phase_index != 3 or (active_day is not None and trading_day <= active_day):
                raise ValueError("回测阶段必须按交易日和盘前、盘中、盘后顺序执行")
            expire_before = str(request["expire_before"])
            for symbol, days in tuple(price_days.items()):
                values = prices[symbol]
                expired = bisect_left(days, expire_before)
                if expired:
                    del days[:expired]
                    del values[:expired]
                if not days:
                    del price_days[symbol]
                    del prices[symbol]
            add_prices(cast(list[dict[str, object]], request.get("prior_before", [])))
            namespace = {"__builtins__": _safe_builtins()}
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compiled, namespace)
            active_day, phase_index = trading_day, 0
        if active_day != trading_day or phase_index >= 3 or phase != phases[phase_index]:
            raise ValueError("回测阶段必须按交易日和盘前、盘中、盘后顺序执行")
        if phase == "after_market":
            add_prices(cast(list[dict[str, object]], request.get("prior_after", [])))
            add_prices(cast(list[dict[str, object]], request.get("today_after", [])))
        elif phase == "on_market":
            add_prices(cast(list[dict[str, object]], request.get("prior_intraday", [])))
        universe = set(prices)
        if phase != "before_market":
            universe.update(
                str(item) for item in cast(list[object], request.get("today_symbols", []))
            )
        records = cast(dict[str, object], request.get("records", {}))
        context = {
            "universe": sorted(universe),
            "prices": prices,
            "market_values": {},
            "trading_day": trading_day,
            "phase": phase,
            "current_prices": request.get("current_prices", {}) if phase == "on_market" else {},
            "records": records.get(phase, {}),
            "positions": request.get("positions", {}),
            "cash": request.get("cash"),
            "costs": request.get("costs", {}),
            "fee_rate": request.get("fee_rate", "0.0003"),
            "slippage_rate": request.get("slippage_rate", "0"),
            "runtime": request.get("runtime", "backtest"),
            "allow_mock": request.get("allow_mock", False),
            "decision_at": request.get("decision_at", "9999-12-31T00:00:00+00:00"),
            "strategy_state": strategy_state,
        }
        result = _execute_call(namespace, parameters, {"context": context, "phase": phase})
        if result.get("ok"):
            strategy_state = cast(dict[str, object], result["state"])
        phase_index += 1
        return result

    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get("stop"):
                break
            requested_phases = (request["phase"],) if "phase" in request else phases
            results = [execute_phase(request, phase) for phase in requested_phases]
            _stream_reply({"ok": True, "results": results})
        except Exception as error:
            _stream_reply({"ok": False, "error": f"{type(error).__name__}: {error}"})


def _stream_reply(payload: dict[str, object]) -> None:
    assert sys.__stdout__ is not None
    sys.__stdout__.write(json.dumps(payload, ensure_ascii=True, default=str) + "\n")
    sys.__stdout__.flush()


def _safe_builtins() -> dict[str, object]:
    return {
        "Decimal": Decimal,
        "sorted": sorted,
        "set": set,
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


def _execute_call(
    namespace: dict[str, object], parameters: object, call: object
) -> dict[str, object]:
    output = io.StringIO()
    state = {}
    runtime_context = None
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
                state = deepcopy(context.get("strategy_state", {}))
                runtime_context = RuntimeContext(
                    context,
                    state=state,
                    quote_provider=_request_quotes if context.get("runtime") == "live" else None,
                )
                signals = function(runtime_context, raw_parameters)
            if signals is None:
                signals = []
        return {
            "ok": True,
            "signals": signals,
            "stdout": output.getvalue()[:65536],
            "state": state,
            "mock_usage": runtime_context.mock_usage if runtime_context else [],
        }
    except Exception as error:
        return {
            "ok": False,
            "signals": [],
            "stdout": output.getvalue()[:65536],
            "error": f"{type(error).__name__}: {error}",
        }


if __name__ == "__main__":
    stream_main() if "--stream" in sys.argv else main()
