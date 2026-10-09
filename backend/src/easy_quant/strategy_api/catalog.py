"""随平台发布的只读策略公共库说明。"""

import json
from pathlib import Path

LIBRARY = json.loads(Path(__file__).with_name("library-v1.json").read_text(encoding="utf-8"))
