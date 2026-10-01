from __future__ import annotations

from datetime import datetime

from easy_quant.application.ports.core import IdGenerator
from easy_quant.domain.live_tracking.entities import (
    LiveInstance,
    Recommendation,
    recommendation_business_key,
)
from easy_quant.domain.live_tracking.ledger import (
    ActualPortfolio,
    PortfolioLedgerEntry,
    rebuild_portfolio,
)


class LiveAnalysisService:
    def __init__(self, ids: IdGenerator) -> None:
        self.ids = ids
        self.recommendations: dict[str, Recommendation] = {}

    def create_recommendation(
        self,
        instance: LiveInstance,
        decision_at: datetime,
        instrument_id: str,
        signal_key: str,
        action: str,
        quantity: str,
        reason: str,
    ) -> Recommendation:
        key = recommendation_business_key(
            instance.id, instance.strategy_version_id, decision_at, instrument_id, signal_key
        )
        if key in self.recommendations:
            return self.recommendations[key]
        item = Recommendation(
            self.ids.new(),
            instance.id,
            instance.owner_id,
            instance.strategy_version_id,
            decision_at,
            instrument_id,
            signal_key,
            action,
            quantity,
            reason,
            key,
        )
        self.recommendations[key] = item
        return item

    @staticmethod
    def actual_portfolio(
        initial_cash: object, ledger: list[PortfolioLedgerEntry]
    ) -> ActualPortfolio:
        from decimal import Decimal

        return rebuild_portfolio(Decimal(str(initial_cash)), ledger)
