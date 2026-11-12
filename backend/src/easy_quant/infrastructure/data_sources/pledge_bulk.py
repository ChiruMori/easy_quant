"""质押全市场原始接口；每一页经过同一个请求预算。"""

import json


class EastMoneyPledgeSource:
    key = "eastmoney"

    def __init__(self, client):
        self.client = client

    def fetch(self, request):
        day = str(request.parameters["date"])
        day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPT_CSDC_LIST",
            "columns": "ALL",
            "pageSize": 1,
            "pageNumber": 1,
            "sortColumns": "TRADE_DATE",
            "sortTypes": -1,
            "filter": f"(TRADE_DATE<='{day}')",
        }
        response = self.client.get(url, params=params)
        response.raise_for_status()
        result = response.json().get("result")
        if not result or not result.get("data"):
            raise ValueError("质押来源未返回最近披露日期")
        latest = str(result["data"][0]["TRADE_DATE"])[:10]
        params.update(
            pageSize=500,
            sortColumns="SECURITY_CODE",
            sortTypes=1,
            filter=f"(TRADE_DATE='{latest}')",
        )
        rows, page, total, pages = [], 1, None, 1
        while page <= pages:
            params["pageNumber"] = page
            response = self.client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            result = payload.get("result")
            if payload.get("success") is not True or not result:
                raise ValueError("质押来源分页失败")
            if total is not None and total != int(result["count"]):
                raise ValueError("质押分页总量变化")
            total, pages = int(result["count"]), int(result["pages"])
            rows.extend(result["data"])
            page += 1
        if len(rows) != total or len({row["SECURITY_CODE"] for row in rows}) != total:
            raise ValueError("质押分页不完整或重复")
        return json.dumps(
            [
                {
                    **row,
                    "symbol": row["SECURITY_CODE"],
                    "交易日期": latest,
                    "pledge_ratio": row.get("PLEDGE_RATIO"),
                }
                for row in rows
            ]
        ).encode(), "application/json"
