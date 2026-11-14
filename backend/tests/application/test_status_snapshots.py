from easy_quant.infrastructure.persistence.repositories.runtime import InMemoryMarketDataStore


def test_status_only_saves_changes_and_retains_first_visibility_and_return_transitions():
    store = InMemoryMarketDataStore({}, {}, set())

    def snapshot(index, status, source="eastmoney"):
        return {
            "symbol": "000001",
            "name": "股票",
            "status": status,
            "is_st": False,
            "record_key": str(index),
            "available_at": f"2026-09-{index:02d}T00:00:00+00:00",
            "as_of_day": f"2026-09-{index:02d}",
            "source": source,
            "previous_status": "active",
        }

    first = snapshot(1, "active")
    assert store.upsert_records("security-status", [first]) == 0
    assert store.upsert_records("security-status", [snapshot(2, "active", "sina")]) == 1
    assert store.list_records("security-status") == [first]
    store.upsert_records("security-status", [snapshot(3, "suspended"), snapshot(4, "active")])
    assert [row["status"] for row in store.list_records("security-status")] == [
        "active",
        "suspended",
        "active",
    ]
    # 兼容真实库既存重复记录：只读视图折叠，不改写旧行。
    store.market_records[("security-status", "legacy")] = snapshot(5, "active")
    assert len(store.list_records("security-status")) == 3
    assert len(store.market_records) == 4


def test_explicit_suspension_interval_correction_is_kept_but_plain_refresh_does_not_erase_it():
    store = InMemoryMarketDataStore({}, {}, set())
    row = {
        "symbol": "000001",
        "name": "股票",
        "status": "suspended",
        "record_key": "1",
        "available_at": "2026-09-01T00:00:00+00:00",
        "suspension_start": "2026-08-01",
        "suspension_end": None,
    }
    store.upsert_records("security-status", [row])
    store.upsert_records(
        "security-status",
        [
            {
                **row,
                "record_key": "2",
                "available_at": "2026-09-02T00:00:00+00:00",
                "suspension_start": "2026-08-02",
            }
        ],
    )
    plain = {key: value for key, value in row.items() if not key.startswith("suspension_")}
    assert (
        store.upsert_records(
            "security-status",
            [{**plain, "record_key": "3", "available_at": "2026-09-03T00:00:00+00:00"}],
        )
        == 1
    )
    assert len(store.list_records("security-status")) == 2
    assert store.list_records("security-status")[-1]["suspension_start"] == "2026-08-02"
