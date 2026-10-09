from __future__ import annotations

import ast

from easy_quant.domain.shared.errors import ValidationError

FORBIDDEN_NAMES = {"breakpoint", "eval", "exec", "open", "__import__"}
DEFAULT_HISTORY_TRADING_DAYS = 250
MAX_HISTORY_TRADING_DAYS = 2500


def extract_history_trading_days(source_code: str) -> int:
    declaration: int | None = None
    for node in ast.parse(source_code).body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "HISTORY_TRADING_DAYS"
            for target in node.targets
        ):
            continue
        value = node.value
        if (
            declaration is not None
            or not isinstance(value, ast.Constant)
            or type(value.value) is not int
        ):
            raise ValidationError("HISTORY_TRADING_DAYS 必须是唯一的整数常量")
        declaration = value.value
    if declaration is None:
        return DEFAULT_HISTORY_TRADING_DAYS
    if not 1 <= declaration <= MAX_HISTORY_TRADING_DAYS:
        raise ValidationError(f"HISTORY_TRADING_DAYS 必须在 1 至 {MAX_HISTORY_TRADING_DAYS} 之间")
    return declaration


def extract_factor_dependencies(source_code: str) -> set[str]:
    tree = ast.parse(source_code)
    datasets: set[str] = set()
    factor_datasets = {
        "market.daily-bars": "daily-bars",
        "technical.ma": "daily-bars",
        "technical.rsi": "daily-bars",
        "technical.macd": "daily-bars",
        "stat.expected-return": "daily-bars",
        "market.value": "market-values",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        helpers = {
            "security_info": {"security-status", "sw-industry-memberships"},
            "securities": {"sw-industry-memberships", "security-status"},
            "financials": {"financial-indicators"},
            "valuation": {"market-values"},
        }
        datasets.update(helpers.get(node.func.attr, set()))
        if (
            node.func.attr != "factor"
            or not node.args
            or not isinstance(node.args[0], ast.Constant)
        ):
            continue
        factor_key = node.args[0].value
        if isinstance(factor_key, str) and factor_key in factor_datasets:
            datasets.add(factor_datasets[factor_key])
        if factor_key in {"fundamental.latest", "fundamental.history"}:
            dataset = next(
                (
                    keyword.value.value
                    for keyword in node.keywords
                    if keyword.arg == "dataset" and isinstance(keyword.value, ast.Constant)
                ),
                None,
            )
            if isinstance(dataset, str):
                datasets.add(dataset)
    return datasets


class PythonStrategyValidator:
    def validate(self, source_code: str) -> None:
        try:
            tree = ast.parse(source_code)
        except SyntaxError as error:
            raise ValidationError("策略语法错误", {"line": error.lineno or 0}) from error
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        entries = {
            node.name
            for node in functions
            if node.name in {"before_market", "on_market", "after_market"}
            and len(node.args.args) == 2
        }
        required_hooks = {"before_market", "on_market", "after_market"}
        if entries != required_hooks:
            raise ValidationError(
                "策略必须完整定义 before_market、on_market、after_market 三个钩子",
                {"missing_hooks": sorted(required_hooks - entries)},
            )
        invalid_hooks = [
            node.name
            for node in functions
            if node.name in {"before_market", "on_market", "after_market"}
            and len(node.args.args) != 2
        ]
        if invalid_hooks:
            raise ValidationError("策略钩子必须接收 context 和 parameters 两个参数")
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                raise ValidationError("策略不允许导入模块")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in FORBIDDEN_NAMES
            ):
                raise ValidationError("策略使用了禁止的函数", {"name": node.func.id})
        extract_history_trading_days(source_code)
