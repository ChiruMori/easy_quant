from __future__ import annotations

from typing import Protocol

from easy_quant.domain.strategies.entities import StrategyDefinition, StrategyRun, StrategyVersion


class StrategyRepository(Protocol):
    def add_definition(self, strategy: StrategyDefinition) -> None: ...
    def get_definition(self, strategy_id: str) -> StrategyDefinition | None: ...
    def add_version(self, version: StrategyVersion) -> None: ...
    def versions(self, strategy_id: str) -> tuple[StrategyVersion, ...]: ...


class StrategyValidator(Protocol):
    def validate(self, source_code: str) -> None: ...


class StrategyRunner(Protocol):
    def run(self, version: StrategyVersion, parameters: dict[str, object]) -> StrategyRun: ...
