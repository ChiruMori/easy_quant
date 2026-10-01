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
