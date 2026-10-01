from __future__ import annotations

import hashlib

from easy_quant.application.ports.core import Clock, IdGenerator
from easy_quant.application.ports.strategies import StrategyRepository, StrategyValidator
from easy_quant.domain.shared.errors import NotFoundError
from easy_quant.domain.strategies.entities import StrategyDefinition, StrategyVersion


class StrategyService:
    def __init__(
        self,
        repository: StrategyRepository,
        validator: StrategyValidator,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self.repository, self.validator, self.clock, self.ids = repository, validator, clock, ids

    def create(
        self, owner_id: str, name: str, source_code: str, description: str = ""
    ) -> tuple[StrategyDefinition, StrategyVersion]:
        strategy = StrategyDefinition(self.ids.new(), owner_id, name, description)
        self.repository.add_definition(strategy)
        return strategy, self.add_version(strategy.id, source_code)

    def add_version(self, strategy_id: str, source_code: str) -> StrategyVersion:
        self.validator.validate(source_code)
        strategy = self.repository.get_definition(strategy_id)
        if strategy is None:
            raise NotFoundError("strategy")
        previous = self.repository.versions(strategy_id)
        version = StrategyVersion(
            self.ids.new(),
            strategy_id,
            len(previous) + 1,
            source_code,
            hashlib.sha256(source_code.encode()).hexdigest(),
            self.clock.now(),
            previous[-1].id if previous else None,
        )
        self.repository.add_version(version)
        strategy.current_version_id = version.id
        return version
