"""固定无公司行为的离线 fixture；生产仓储不生成任何隐式覆盖证明。"""

from typing import Any

from easy_quant.infrastructure.persistence.repositories.runtime import InMemoryMarketDataStore


class VerifiedFixtureMarketStore(InMemoryMarketDataStore):
    fixture_state: Any = None

    def list_bars(self, *args, **kwargs):
        return [
            {"source": "fixture", "adjustment": "none", **row}
            for row in super().list_bars(*args, **kwargs)
        ]

    def upsert_bars(self, rows):
        return super().upsert_bars(
            [{"source": "fixture", "adjustment": "none", **row} for row in rows]
        )

    def list_records(self, dataset_key, symbol=None, *, as_of=None):
        records = super().list_records(dataset_key, symbol, as_of=as_of)
        if dataset_key != "corporate-actions":
            return records
        certified = {row["symbol"] for row in records if row.get("record_kind") == "coverage"}
        symbols = {str(row["symbol"]) for row in self.daily_bars.values()}
        if self.fixture_state is not None:
            for instance in self.fixture_state.live_instances.values():
                symbols.update(instance.get("initial_positions", {}))
                symbols.update(instance.get("positions", {}))
            symbols.update(
                row["symbol"] for row in self.fixture_state.portfolio_ledger if row.get("symbol")
            )
        return records + [
            {
                "record_kind": "coverage",
                "symbol": key,
                "start_day": "1900-01-01",
                "end_day": "2100-12-31",
                "complete": True,
                "event_keys": [],
                "source": "versioned-offline-fixture",
                "evidence": "tests/fakes/corporate_actions.py",
                "available_at": "1900-01-01T00:00:00+00:00",
                "record_key": f"fixture-no-actions-{key}",
            }
            for key in symbols
            if key not in certified and (symbol is None or symbol == key)
        ]
