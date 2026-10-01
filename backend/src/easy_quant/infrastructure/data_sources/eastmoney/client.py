from __future__ import annotations

from collections.abc import Mapping

import httpx


class EastMoneyClient:
    def __init__(self, client: httpx.Client, base_url: str = "https://push2.eastmoney.com") -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")

    def get_json(self, path: str, params: Mapping[str, object]) -> dict[str, object]:
        query = {key: str(value) for key, value in params.items()}
        url = (
            path
            if path.startswith(("http://", "https://"))
            else f"{self.base_url}/{path.lstrip('/')}"
        )
        response = self.client.get(url, params=query)
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("东方财富响应不是 JSON 对象")
        return value
