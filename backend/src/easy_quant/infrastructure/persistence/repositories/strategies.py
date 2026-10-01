from sqlalchemy import select
from sqlalchemy.orm import Session

from easy_quant.domain.strategies.entities import StrategyDefinition, StrategyVersion
from easy_quant.infrastructure.persistence.models.strategies import (
    StrategyModel,
    StrategyVersionModel,
)


class InMemoryStrategyRepository:
    def __init__(self) -> None:
        self.definitions: dict[str, StrategyDefinition] = {}
        self.version_items: dict[str, list[StrategyVersion]] = {}

    def add_definition(self, strategy):
        self.definitions[strategy.id] = strategy

    def get_definition(self, strategy_id):
        return self.definitions.get(strategy_id)

    def add_version(self, version):
        self.version_items.setdefault(version.strategy_id, []).append(version)

    def versions(self, strategy_id):
        return tuple(self.version_items.get(strategy_id, ()))


class SqlAlchemyStrategyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @property
    def definitions(self) -> dict[str, StrategyDefinition]:
        return {
            row.id: self._definition(row) for row in self.session.scalars(select(StrategyModel))
        }

    def add_definition(self, strategy: StrategyDefinition) -> None:
        self.session.add(
            StrategyModel(
                id=strategy.id,
                owner_id=strategy.owner_id,
                name=strategy.name,
                description=strategy.description,
                current_version_id=strategy.current_version_id,
            )
        )
        self.session.commit()

    def get_definition(self, strategy_id: str) -> StrategyDefinition | None:
        row = self.session.get(StrategyModel, strategy_id)
        return None if row is None else self._definition(row)

    def add_version(self, version: StrategyVersion) -> None:
        self.session.add(
            StrategyVersionModel(
                id=version.id,
                strategy_id=version.strategy_id,
                number=version.number,
                source_code=version.source_code,
                content_sha256=version.content_sha256,
                parent_version_id=version.parent_version_id,
                created_at=version.created_at,
            )
        )
        row = self.session.get(StrategyModel, version.strategy_id)
        if row is not None:
            row.current_version_id = version.id
        self.session.commit()

    def versions(self, strategy_id: str) -> tuple[StrategyVersion, ...]:
        rows = self.session.scalars(
            select(StrategyVersionModel)
            .where(StrategyVersionModel.strategy_id == strategy_id)
            .order_by(StrategyVersionModel.number)
        )
        return tuple(
            StrategyVersion(
                row.id,
                row.strategy_id,
                row.number,
                row.source_code,
                row.content_sha256,
                row.created_at,
                row.parent_version_id,
            )
            for row in rows
        )

    @staticmethod
    def _definition(row: StrategyModel) -> StrategyDefinition:
        return StrategyDefinition(
            row.id, row.owner_id, row.name, row.description, row.current_version_id
        )
