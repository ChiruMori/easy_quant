from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

TRANSIENT_KEYS = {"timestamp", "ts", "uuid", "nonce", "signature", "sign", "request_id"}


def canonical_parameters(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): canonical_parameters(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key).casefold() not in TRANSIENT_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [canonical_parameters(item) for item in value]
    return value


def semantic_request_identity(dataset_key: str, parameters: Mapping[str, object]) -> str:
    canonical = {"dataset": dataset_key, "parameters": canonical_parameters(parameters)}
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
