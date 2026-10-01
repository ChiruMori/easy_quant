from datetime import timedelta

from easy_quant.factors.context import FactorContext


class Gateway:
    def __init__(self, rows):
        self.rows = rows

    def records(self, dataset, symbol):
        return self.rows


def test_future_data_is_invisible_and_rows_preserve_time_order(fixed_now) -> None:
    rows = [
        {"available_at": fixed_now, "day": 1},
        {"available_at": fixed_now + timedelta(days=1), "day": 2},
    ]
    visible = FactorContext(Gateway(rows), fixed_now).read("daily-bars", "000001")
    assert [row["day"] for row in visible] == [1]
