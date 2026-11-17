"""策略可见的数值接口契约；AST 检查不导入第三方库。"""

import ast

from easy_quant.domain.shared.errors import ValidationError

NUMPY_NAMES = frozenset(
    {
        "array",
        "asarray",
        "float64",
        "int64",
        "isfinite",
        "isnan",
        "nan",
        "where",
        "arange",
        "zeros",
        "ones",
        "full",
        "concatenate",
        "diff",
        "mean",
        "std",
        "sum",
        "min",
        "max",
        "abs",
        "sqrt",
        "log",
        "exp",
        "clip",
        "round",
    }
)


def validate_numeric_imports(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name not in {"talib", "numpy"} for alias in node.names):
                raise ValidationError("策略仅允许导入 talib 和受限 numpy")
        elif isinstance(node, ast.ImportFrom):
            if (
                node.level
                or node.module not in {"talib", "numpy"}
                or any(
                    alias.name.startswith("_")
                    or alias.name == "*"
                    or (node.module == "numpy" and alias.name not in NUMPY_NAMES)
                    or (
                        node.module == "talib"
                        and not alias.name.isupper()
                        and alias.name != "MA_Type"
                    )
                    for alias in node.names
                )
            ):
                raise ValidationError("策略仅允许导入公开数值函数，禁止子模块和通配导入")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or node.attr in {"tofile", "dump", "dumps", "ctypes"}:
                raise ValidationError("策略不允许访问内部属性或数组文件接口")
        elif isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValidationError("策略不允许访问内部名称")
