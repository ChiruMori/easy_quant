import json

import pandas as pd

from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.infrastructure.data_sources.akshare.adapters import AkShareSource


def test_akshare_adapter_serializes_dataframe_stably() -> None:
    source = AkShareSource({"shareholders": lambda **_: pd.DataFrame([{"b": 2, "a": 1}])})
    payload, media_type = source.fetch(SemanticRequest("shareholders", {}, "id"))
    assert json.loads(payload) == [{"a": 1, "b": 2}]
    assert media_type == "application/json"
