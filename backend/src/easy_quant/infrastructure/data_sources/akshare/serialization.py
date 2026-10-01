from __future__ import annotations

import json

import pandas as pd


def stable_dataframe_bytes(frame: pd.DataFrame) -> bytes:
    normalized = frame.copy()
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    normalized = normalized.where(pd.notna(normalized), None)
    rows = normalized.to_dict(orient="records")
    return json.dumps(
        rows, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")
    ).encode()
