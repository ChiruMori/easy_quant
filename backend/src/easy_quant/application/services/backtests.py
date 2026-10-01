from __future__ import annotations

from easy_quant.application.ports.core import Clock, IdGenerator
from easy_quant.domain.backtesting.engine import StrategyAtDay, run_daily_backtest
from easy_quant.domain.backtesting.entities import BacktestConfig, BacktestRun, BacktestStatus
from easy_quant.domain.backtesting.execution import MarketBar


class BacktestService:
    def __init__(self, clock: Clock, ids: IdGenerator, application_version: str = "0.1.0") -> None:
        self.clock, self.ids, self.application_version = clock, ids, application_version
        self.runs: dict[str, BacktestRun] = {}

    def create(self, owner_id: str, config: BacktestConfig, snapshot_id: str) -> BacktestRun:
        run = BacktestRun(
            self.ids.new(),
            owner_id,
            config,
            snapshot_id,
            self.application_version,
            created_at=self.clock.now(),
        )
        self.runs[run.id] = run
        return run

    def execute(self, run_id: str, bars: list[MarketBar], strategy: StrategyAtDay) -> BacktestRun:
        run = self.runs[run_id]
        run.status, run.progress = BacktestStatus.RUNNING, 10
        try:
            periods, trades, metrics = run_daily_backtest(run.config, bars, strategy)
            run.periods = periods
            run.trades = list(trades)
            run.metrics = metrics
            run.status, run.progress = BacktestStatus.SUCCEEDED, 100
        except Exception as error:
            run.status, run.error = BacktestStatus.FAILED, str(error)
        return run
