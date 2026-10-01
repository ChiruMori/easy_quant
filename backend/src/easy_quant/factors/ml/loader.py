from __future__ import annotations

import hashlib
import json
from pathlib import Path


def load_weights(manifest_path: Path, model_key: str) -> dict[str, float]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = manifest["models"][model_key]
    path = manifest_path.parent / item["file"]
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != item["sha256"]:
        raise ValueError("模型权重摘要不匹配")
    weights = json.loads(payload)
    if not isinstance(weights, dict):
        raise ValueError("模型权重格式无效")
    return {str(key): float(value) for key, value in weights.items()}
