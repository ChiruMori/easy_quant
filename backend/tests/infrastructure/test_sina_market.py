import json

import httpx
import pytest

from easy_quant.bootstrap import ensure_dataset_catalog
from easy_quant.domain.market_data.entities import SemanticRequest
from easy_quant.infrastructure.data_sources.sina_market import SinaMarketSource


@pytest.mark.parametrize("broken", [None, "duplicate", "short", "changed", "nonfinite"])
def test_sina_complete_paging_and_valuation_units(broken):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("getHQNodeStockCount"):
            return httpx.Response(
                200, json="102" if broken == "changed" and len(calls) > 1 else "101"
            )
        page = int(request.url.params["page"])
        rows = [
            {
                "code": f"{index:06d}",
                "name": "股票",
                "per": "-4.5",
                "pb": None,
                "mktcap": "123.456789",
                "nmc": "99",
            }
            for index in (range(100) if page == 1 else range(100, 101))
        ]
        if broken == "duplicate" and page == 2:
            rows[0]["code"] = "000000"
        if broken == "short":
            rows = []
        if broken == "nonfinite":
            rows[0]["mktcap"] = "NaN"
        return httpx.Response(200, json=rows)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        source = SinaMarketSource(client)
        if broken:
            with pytest.raises(ValueError):
                source.fetch(SemanticRequest("market-values", {}, "id"))
        else:
            rows = json.loads(source.fetch(SemanticRequest("market-values", {}, "id"))[0])["data"][
                "diff"
            ]
            assert len(rows) == 101 and len(calls) == 4
            assert (
                rows[0]["market_cap"] == "1234567.890000"
                and rows[0]["pe_ratio"] == "-4.5"
                and rows[0]["pb_ratio"] is None
            )


def test_catalog_replaces_dead_market_sources_without_reenabling_disabled_dataset():
    datasets = [{"key": "market-values", "sources": [{"key": "eastmoney", "enabled": False}]}]
    ensure_dataset_catalog(datasets)
    assert datasets[0]["sources"] == [{"key": "sina", "name": "新浪财经（直连）", "enabled": False}]
    before = json.dumps(datasets)
    ensure_dataset_catalog(datasets)
    assert json.dumps(datasets) == before
