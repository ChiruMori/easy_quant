from __future__ import annotations

import ast

from easy_quant.domain.shared.errors import ValidationError

FORBIDDEN_NAMES = {"breakpoint", "eval", "exec", "open", "__import__"}
DEFAULT_HISTORY_TRADING_DAYS = 250
MAX_HISTORY_TRADING_DAYS = 2500


def _tail_history_window(tree: ast.AST, call: ast.Call) -> int:
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    parent = parents.get(call)
    uses: list[ast.AST] = [call]
    if (
        isinstance(parent, ast.Assign)
        and len(parent.targets) == 1
        and isinstance(parent.targets[0], ast.Name)
    ):
        name = parent.targets[0].id
        uses = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load)
        ]
    windows = [1]
    for use in uses:
        subscript = parents.get(use)
        if not isinstance(subscript, ast.Subscript) or subscript.value is not use:
            return DEFAULT_HISTORY_TRADING_DAYS
        index = subscript.slice
        if (
            isinstance(index, ast.UnaryOp)
            and isinstance(index.op, ast.USub)
            and isinstance(index.operand, ast.Constant)
            and type(index.operand.value) is int
            and index.operand.value > 0
        ):
            windows.append(index.operand.value)
        else:
            return DEFAULT_HISTORY_TRADING_DAYS
    return max(windows)


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
        windows: list[int] = []
        tree = ast.parse(source_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "data":
                windows.append(DEFAULT_HISTORY_TRADING_DAYS)
                continue
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr in {"history", "daily_bars"}:
                windows.append(DEFAULT_HISTORY_TRADING_DAYS)
                continue
            if node.func.attr not in {"factor", "library"}:
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                windows.append(DEFAULT_HISTORY_TRADING_DAYS)
                continue
            key = node.args[0].value
            if key == "market.daily-bars":
                required = _tail_history_window(tree, node)
                if required > MAX_HISTORY_TRADING_DAYS:
                    raise ValidationError("因子所需历史超过 2500 个交易日")
                windows.append(required)
                continue
            from easy_quant.factors.registry import build_default_registry

            definition = next(
                (item for item in build_default_registry().list() if item.key == key), None
            )
            if definition is None:
                continue
            if definition.history_parameter is None:
                windows.append(DEFAULT_HISTORY_TRADING_DAYS)
                continue
            if any(keyword.arg is None for keyword in node.keywords):
                windows.append(DEFAULT_HISTORY_TRADING_DAYS)
                continue
            value = next(
                (kw.value for kw in node.keywords if kw.arg == definition.history_parameter), None
            )
            if value is None:
                window = int(str(definition.defaults[definition.history_parameter]))
            elif isinstance(value, ast.Constant) and type(value.value) is int:
                window = value.value
            else:
                windows.append(DEFAULT_HISTORY_TRADING_DAYS)
                continue
            if not 1 <= window <= MAX_HISTORY_TRADING_DAYS:
                raise ValidationError("因子窗口必须在 1 至 2500 之间")
            required = window + definition.history_extra
            if required > MAX_HISTORY_TRADING_DAYS:
                raise ValidationError("因子所需历史超过 2500 个交易日")
            windows.append(required)
        return max(windows) if windows else DEFAULT_HISTORY_TRADING_DAYS
    if not 1 <= declaration <= MAX_HISTORY_TRADING_DAYS:
        raise ValidationError(f"HISTORY_TRADING_DAYS 必须在 1 至 {MAX_HISTORY_TRADING_DAYS} 之间")
    return declaration


def extract_factor_dependencies(source_code: str) -> set[str]:
    tree = ast.parse(source_code)
    datasets: set[str] = set()
    from easy_quant.factors.registry import build_default_registry

    factor_datasets = {item.key: item.datasets for item in build_default_registry().list()}
    factor_datasets.update(
        {"market.daily-bars": ("daily-bars",), "market.value": ("market-values",)}
    )
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
            node.func.attr not in {"factor", "library"}
            or not node.args
            or not isinstance(node.args[0], ast.Constant)
        ):
            continue
        factor_key = node.args[0].value
        if isinstance(factor_key, str) and factor_key in factor_datasets:
            datasets.update(factor_datasets[factor_key])
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
