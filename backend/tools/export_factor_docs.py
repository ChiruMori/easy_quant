"""从平台只读元数据导出当前因子说明，避免页面与文档分叉。"""

from pathlib import Path

from easy_quant.factors.alpha101_docs import OPERATOR_GUIDE
from easy_quant.factors.registry import build_default_registry


def main() -> None:
    content = [
        "# 因子计算逻辑与结果含义",
        "",
        "本文由平台当前因子元数据导出，与因子目录使用相同说明。",
        "更新命令：`uv run --project backend python backend/tools/export_factor_docs.py`。",
        "",
        "## Alpha101 算子约定",
        "",
        OPERATOR_GUIDE,
        "",
        "数据可见性、缺失处理、输入口径与股票池范围见[对标因子](对标因子.md)。",
        "",
    ]
    for item in build_default_registry().list():
        content.extend([f"## {item.key}：{item.name}", ""])
        for line in item.description.split("\n算子说明：")[0].splitlines():
            if line.startswith("公式："):
                content.extend(["公式：", "", "```text", line.removeprefix("公式："), "```", ""])
            else:
                content.extend([line, ""])
    target = Path(__file__).resolve().parents[2] / "docs" / "因子计算逻辑.md"
    target.write_text("\n".join(content), encoding="utf-8")


if __name__ == "__main__":
    main()
