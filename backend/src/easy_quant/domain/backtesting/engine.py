from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from easy_quant.domain.backtesting.entities import (
    BacktestConfig,
    BacktestPeriod,
    Portfolio,
    SimulatedTrade,
)
from easy_quant.domain.backtesting.execution import MarketBar, execute_signal
from easy_quant.domain.backtesting.metrics import calculate_metrics
from easy_quant.domain.strategies.entities import Signal

StrategyAtDay = Callable[[date], list[Signal]]
PhasedStrategyAtDay = Callable[[date, str], list[Signal]]


def run_daily_backtest(
    config: BacktestConfig,
    bars: list[MarketBar],
    strategy: StrategyAtDay,
) -> tuple[list[BacktestPeriod], list[SimulatedTrade], dict[str, Decimal | int | None]]:
    portfolio = Portfolio(config.initial_cash)
    periods: list[BacktestPeriod] = []
    trades: list[SimulatedTrade] = []
    by_day: dict[date, list[MarketBar]] = {}
    for bar in bars:
        if config.start_day <= bar.trading_day <= config.end_day:
            by_day.setdefault(bar.trading_day, []).append(bar)
    for trading_day in sorted(by_day):
        visible_bars = {bar.symbol: bar for bar in by_day[trading_day]}
        for signal in strategy(trading_day):
            bar = visible_bars.get(signal.symbol)
            if bar is None:
                continue
            trade = execute_signal(portfolio, signal, bar, config.fee_rate, config.slippage_rate)
            if trade is not None:
                trades.append(trade)
        positions_value = sum(
            (
                visible_bars[symbol].close * quantity
                for symbol, quantity in portfolio.positions.items()
                if symbol in visible_bars
            ),
            Decimal(0),
        )
        periods.append(
            BacktestPeriod(
                trading_day, portfolio.cash + positions_value, portfolio.cash, positions_value
            )
        )
    turnover = (
        sum((trade.price * trade.quantity for trade in trades), Decimal(0)) / config.initial_cash
    )
    metrics = calculate_metrics([period.equity for period in periods], turnover, len(trades))
    return periods, trades, metrics


def run_phased_daily_backtest(
    config: BacktestConfig,
    bars: list[MarketBar],
    strategy: PhasedStrategyAtDay,
) -> tuple[list[BacktestPeriod], list[SimulatedTrade], dict[str, Decimal | int | None]]:
    """按盘前、盘中、盘后顺序运行策略；回测路径没有通知副作用。

    盘前信号按开盘价成交，盘中以开收盘均值检查指定方向的触发条件，
    盘后信号按收盘价成交。这样不会把盘中条件错误地统一按收盘价执行。
    """

    by_day: dict[date, list[MarketBar]] = {}
    for bar in bars:
        if config.start_day <= bar.trading_day <= config.end_day:
            by_day.setdefault(bar.trading_day, []).append(bar)
    session = PhasedBacktestSession(config)
    for trading_day in sorted(by_day):
        session.advance(
            trading_day,
            by_day[trading_day],
            lambda phase, day=trading_day: strategy(day, phase),
        )
    return session.finish()


class PhasedBacktestSession:
    """逐交易日推进的纯领域回测状态机。"""

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self.portfolio = Portfolio(config.initial_cash)
        self.periods: list[BacktestPeriod] = []
        self.trades: list[SimulatedTrade] = []

    def advance(
        self,
        trading_day: date,
        day_bars: list[MarketBar],
        strategy: Callable[[str], list[Signal]],
    ) -> None:
        visible_bars = {bar.symbol: bar for bar in day_bars}
        for phase in ("before_market", "on_market", "after_market"):
            for signal in strategy(phase):
                bar = visible_bars.get(signal.symbol)
                if bar is None:
                    continue
                reference_price = _phase_price(phase, signal, bar)
                if reference_price is None:
                    continue
                trade = execute_signal(
                    self.portfolio,
                    signal,
                    bar,
                    self.config.fee_rate,
                    self.config.slippage_rate,
                    reference_price,
                )
                if trade is not None:
                    self.trades.append(trade)
        positions_value = sum(
            (
                visible_bars[symbol].close * quantity
                for symbol, quantity in self.portfolio.positions.items()
                if symbol in visible_bars
            ),
            Decimal(0),
        )
        self.periods.append(
            BacktestPeriod(
                trading_day,
                self.portfolio.cash + positions_value,
                self.portfolio.cash,
                positions_value,
            )
        )

    def finish(
        self,
    ) -> tuple[list[BacktestPeriod], list[SimulatedTrade], dict[str, Decimal | int | None]]:
        turnover = (
            sum((trade.price * trade.quantity for trade in self.trades), Decimal(0))
            / self.config.initial_cash
        )
        metrics = calculate_metrics(
            [period.equity for period in self.periods], turnover, len(self.trades)
        )
        return self.periods, self.trades, metrics


def _phase_price(phase: str, signal: Signal, bar: MarketBar) -> Decimal | None:
    if phase == "before_market":
        return bar.open if bar.open is not None else bar.close
    if phase == "after_market":
        return bar.close
    price = ((bar.open if bar.open is not None else bar.close) + bar.close) / 2
    if signal.trigger_price is None:
        return price
    operator = signal.trigger_operator or ("lte" if signal.action == "buy" else "gte")
    triggered = (
        price <= signal.trigger_price if operator == "lte" else price >= signal.trigger_price
    )
    return price if triggered else None
