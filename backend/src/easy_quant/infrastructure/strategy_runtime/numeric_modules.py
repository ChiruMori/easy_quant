"""仅向策略提供 TA-Lib 计算函数与 NumPy 数值工具，不暴露真实模块。"""

from types import SimpleNamespace

from easy_quant.strategy_api.imports import NUMPY_NAMES, PANDAS_NAMES


def numeric_importer():
    modules = {}

    def load(name, globals=None, locals=None, fromlist=(), level=0):
        # NumPy dtype/array 的 C 层 str/repr 使用调用者 builtins 做固定导入。
        # 用户源码的 AST 仍禁止子模块与 __import__，不能取得真实模块。
        if name in {"numpy._core._dtype", "numpy._core.arrayprint"} and not level and not fromlist:
            return __import__(name, globals, locals, fromlist, level)
        if level or name not in {"talib", "numpy", "pandas"}:
            raise ImportError("策略仅允许导入 talib、受限 numpy 和 pandas")
        # 只在策略真正导入时加载原生数值库，避免拖慢普通策略和子进程握手。
        if name not in modules:
            if name == "numpy":
                import numpy as np

                modules[name] = SimpleNamespace(**{key: getattr(np, key) for key in NUMPY_NAMES})
            elif name == "pandas":
                import pandas as pd

                modules[name] = SimpleNamespace(**{key: getattr(pd, key) for key in PANDAS_NAMES})
            else:
                import talib

                modules[name] = SimpleNamespace(
                    **{key: getattr(talib, key) for key in talib.get_functions()},
                    MA_Type=SimpleNamespace(
                        **{
                            key: getattr(talib.MA_Type, key)
                            for key in (
                                "SMA",
                                "EMA",
                                "WMA",
                                "DEMA",
                                "TEMA",
                                "TRIMA",
                                "KAMA",
                                "MAMA",
                                "T3",
                            )
                        }
                    ),
                )
        module = modules[name]
        if any(
            item.startswith("_") or item == "*" or not hasattr(module, item)
            for item in (fromlist or ())
        ):
            raise ImportError("未提供该策略数值接口")
        return module

    return load
