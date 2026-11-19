"""同步、只读因子快测，复用受限策略子进程，绝不补造输入。"""

from datetime import date, datetime, time, timedelta
from time import monotonic
from zoneinfo import ZoneInfo

from easy_quant.domain.shared.errors import StateConflictError, ValidationError
from easy_quant.domain.strategies.entities import StrategyVersion
from easy_quant.factors.registry import build_default_registry
from easy_quant.infrastructure.strategy_runtime.runner import SubprocessStrategyRunner

MAX_ROWS = 50_000


def quick_test_factor(container, key, parameters, trading_day, *, timeout_seconds: float = 5):
    started = monotonic()
    definition = build_default_registry().get(key)
    unexpected = parameters.keys() - definition.parameters.keys() - {"symbols"}
    if unexpected:
        raise ValidationError("未知因子参数", {"fields": sorted(unexpected)})
    parameters = {**definition.defaults, **parameters}
    if definition.parameters.keys() - parameters.keys():
        raise ValidationError("请填写全部因子参数")
    symbol = parameters.get("symbol")
    symbols = parameters.get("symbols") or [symbol]
    if (
        not isinstance(symbol, str)
        or not symbol
        or len(symbol) > 32
        or not isinstance(symbols, list)
        or not 1 <= len(symbols) <= 500
        or any(not isinstance(s, str) or not s or len(s) > 32 for s in symbols)
    ):
        raise ValidationError("证券代码或股票池无效（最多500只）")
    for name in definition.integer_parameters:
        try:
            value = int(str(parameters[name]))
        except ValueError as error:
            raise ValidationError("窗口必须为整数") from error
        if not 1 <= value <= 2500:
            raise ValidationError("窗口必须在1–2500之间")
        parameters[name] = value
    cutoff = datetime.combine(trading_day, time.max, ZoneInfo("Asia/Shanghai"))
    window = definition.required_history or (250 if key == "stat.expected-return" else 1)
    if definition.history_parameter:
        window = int(str(parameters[definition.history_parameter])) + definition.history_extra
    if key == "technical.macd":
        window = int(str(parameters["slow"])) + int(str(parameters["signal"]))
    window = min(2500, max(window, 35 if key == "technical.macd" else 1))
    days = sorted(day for day in container.market_data.list_trading_days() if day <= trading_day)[
        -window:
    ]
    start = days[0] if days else trading_day - timedelta(days=window * 2)
    data = {"bars": {}, "records": {}, "decision_at": cutoff.isoformat()}
    from easy_quant.application.services.corporate_actions import (
        decision_snapshot,
        runtime_snapshot,
    )
    from easy_quant.domain.market_data.corporate_actions import CorporateActionBook

    corporate_snapshot = {"corporate_actions": []}
    rows_count = 0

    def check_budget():
        if rows_count > MAX_ROWS:
            raise ValidationError("快测输入超过50000行，请缩小股票池或窗口")
        if monotonic() - started >= timeout_seconds:
            raise StateConflictError("因子快速测试超时，已终止")

    wanted = {str(member) for member in symbols} | {str(symbol)}
    # 市场回归因子按已注册Key的指数后缀读取基准。
    if key.endswith("_000001"):
        wanted.add("sh000001")
    elif key.endswith("_000300"):
        wanted.add("sh000300")
    if "daily-bars" in definition.datasets:
        corporate_snapshot = runtime_snapshot(container.market_data, wanted, check=check_budget)
        data.update(decision_snapshot(corporate_snapshot, cutoff))
    for dataset in definition.datasets:
        for member in sorted(wanted):
            check_budget()
            if dataset == "daily-bars":
                rows = container.market_data.list_bars(start, trading_day, member)
                if rows:
                    CorporateActionBook(corporate_snapshot["corporate_actions"]).require_coverage(
                        member,
                        min(date.fromisoformat(str(row["trading_day"])) for row in rows),
                        trading_day,
                        cutoff,
                    )
                data["bars"][member] = rows
            else:
                rows = container.market_data.list_records(dataset, member, as_of=cutoff)
                data["records"].setdefault(dataset, {})[member] = rows
            rows_count += len(rows)
            check_budget()
    # 平台生成调用代码，不执行用户输入的代码；字符串仅经repr嵌入字面量。
    # 输出通过独立JSON值返回，避免解析Python repr。
    source = (
        "def before_market(context, parameters):\n"
        f"    context.store.set('result', context.factor({key!r}, **parameters))\n"
        "    return []\n"
    )
    version = StrategyVersion("factor-quick-test", "", 0, source, "", cutoff)
    run = SubprocessStrategyRunner(
        timeout_seconds=max(0.001, timeout_seconds - (monotonic() - started))
    ).run(version, parameters, data)
    if run.status != "succeeded":
        raise StateConflictError(
            "因子快速测试超时，已终止" if run.status == "timed_out" else "因子快速测试失败",
            {"reason": run.error},
        )
    return {
        "result": run.state.get("result"),
        "rows": rows_count,
        "elapsed_ms": (monotonic() - started) * 1000,
        "decision_at": cutoff.isoformat(),
        "mock": False,
    }
