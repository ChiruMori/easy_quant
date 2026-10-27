from datetime import timedelta

from easy_quant.factors.context import FactorContext


class Gateway:
    def __init__(self, rows):
        self.rows_value = rows

    def records(self, dataset, symbol):
        return self.rows_value


def test_future_records_are_invisible_and_random_is_repeatable(fixed_now) -> None:
    context = FactorContext(
        Gateway([{"available_at": fixed_now}, {"available_at": fixed_now + timedelta(seconds=1)}]),
        fixed_now,
        42,
    )
    assert len(context.read("bars", "000001")) == 1
    assert context.random().random() == context.random().random()


def test_raw_input_cache_is_bounded_and_returned_nested_values_are_isolated():
    from datetime import UTC, datetime

    from easy_quant.platform_library.context import FactorContext

    class Gateway:
        def records(self, dataset, symbol):
            return [
                {"available_at": datetime(2020, 1, 1, tzinfo=UTC), "nested": [symbol]}
                for _ in range(5)
            ]

    context = FactorContext(Gateway(), datetime(2026, 1, 1, tzinfo=UTC), max_cached_rows=10)
    for i in range(100):
        rows = context.read("daily-bars", str(i))
        nested = rows[0]["nested"]
        assert isinstance(nested, list)
        nested.append("changed")
    assert context._cached_rows <= 10
    assert len(context._records) == 2
    assert context.read("daily-bars", "99")[0]["nested"] == ["99"]
