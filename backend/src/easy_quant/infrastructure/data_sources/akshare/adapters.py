from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.infrastructure.data_sources.akshare.serialization import stable_dataframe_bytes


class AkShareSource:
    key = "akshare"

    def __init__(self, functions: dict[str, Callable[..., pd.DataFrame]]) -> None:
        self.functions = functions

    def fetch(self, request: SemanticRequest) -> tuple[bytes, str]:
        function = self.functions.get(request.dataset_key)
        if function is None:
            raise ValueError(f"AKShare 不支持数据集 {request.dataset_key}")
        return stable_dataframe_bytes(function(**request.parameters)), "application/json"
