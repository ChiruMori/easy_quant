from __future__ import annotations

import hashlib
from dataclasses import replace

from easy_quant.application.ports.core import Clock, IdGenerator
from easy_quant.application.ports.strategies import StrategyRepository, StrategyValidator
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError
from easy_quant.domain.strategies.entities import StrategyDefinition, StrategyState, StrategyVersion


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
        self.validator.validate(source_code)
        strategy = StrategyDefinition(self.ids.new(), owner_id, name, description)
        self.repository.add_definition(strategy)
        version = self.add_version(strategy.id, source_code)
        strategy.current_version_id = version.id
        return strategy, version

    def add_version(
        self,
        strategy_id: str,
        source_code: str,
        *,
        parent_version_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> StrategyVersion:
        self.validator.validate(source_code)
        strategy = self.repository.get_definition(strategy_id)
        if strategy is None:
            raise NotFoundError("strategy")
        previous = self.repository.versions(strategy_id)
        version = StrategyVersion(
            self.ids.new(),
            strategy_id,
            max(strategy.next_version_number, max((row.number for row in previous), default=0) + 1),
            source_code,
            hashlib.sha256(source_code.encode()).hexdigest(),
            self.clock.now(),
            parent_version_id or (previous[-1].id if previous else None),
            name=name if name is not None else strategy.name,
            description=description if description is not None else strategy.description,
        )
        self.repository.add_version(version)
        strategy.current_version_id = version.id
        return version

    def save_draft(
        self,
        version: StrategyVersion,
        name: str,
        description: str,
        source_code: str,
        expected_revision: int,
    ) -> StrategyVersion:
        if version.state != StrategyState.DRAFT:
            raise StateConflictError("该策略已锁定；请确认创建新的草稿版本后编辑")
        self.validator.validate(source_code)
        updated = replace(
            version,
            name=name,
            description=description,
            source_code=source_code,
            content_sha256=hashlib.sha256(source_code.encode()).hexdigest(),
            revision=expected_revision + 1,
        )
        self.repository.save_draft(updated, expected_revision)
        return updated
