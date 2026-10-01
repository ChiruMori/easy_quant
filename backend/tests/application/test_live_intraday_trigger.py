from decimal import Decimal

from easy_quant.application.services.live_runtime import _intraday_triggered


def test_intraday_buy_and_sell_require_price_and_position_conditions() -> None:
    assert _intraday_triggered("buy", Decimal("10"), Decimal("9.9"), 0)
    assert not _intraday_triggered("buy", Decimal("10"), Decimal("10.1"), 0)
    assert not _intraday_triggered("buy", Decimal("10"), Decimal("9.9"), 100)
    assert _intraday_triggered("sell", Decimal("12"), Decimal("12.1"), 100)
    assert not _intraday_triggered("sell", Decimal("12"), Decimal("12.1"), 0)
    assert not _intraday_triggered("sell", None, Decimal("12.1"), 100)
