"""随平台发布的只读策略公共库说明。"""

import json
from pathlib import Path

from easy_quant.platform_library.catalog import build_library_registry

LIBRARY = json.loads(Path(__file__).with_name("library-v1.json").read_text(encoding="utf-8"))

for definition in build_library_registry().list():
    LIBRARY.append(
        {
            "key": definition.key,
            "name": definition.name,
            "signature": f"context.library('{definition.key}', **parameters)",
            "description": definition.description,
            "parameters": "；".join(
                f"{key}：{value}" for key, value in definition.parameters.items()
            ),
            "output": definition.output + "\n" + definition.output_example,
            "example": "context." + definition.example,
            "runtime": "只读 available_at 不晚于决策时点的数据；无记录返回空序列或 None。",
        }
    )
