from dataclasses import replace

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.strategies.entities import (
    StrategyDefinition,
    StrategyState,
    StrategyVersion,
    advanced_strategy_state,
)
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
        self.definitions[version.strategy_id].next_version_number = version.number + 1

    def versions(self, strategy_id):
        return tuple(self.version_items.get(strategy_id, ()))

    def get_version(self, version_id):
        return next(
            (row for rows in self.version_items.values() for row in rows if row.id == version_id),
            None,
        )

    def save_draft(self, version, expected_revision):
        rows = self.version_items.get(version.strategy_id, [])
        for index, current in enumerate(rows):
            if current.id == version.id:
                if current.state != StrategyState.DRAFT or current.revision != expected_revision:
                    raise StateConflictError("策略已变化，请重新加载后编辑")
                rows[index] = version
                return
        raise StateConflictError("策略版本不存在")

    def advance_state(self, version_id, state):
        for rows in self.version_items.values():
            for index, version in enumerate(rows):
                if version.id == version_id:
                    rows[index] = replace(
                        version, state=advanced_strategy_state(version.state, state)
                    )

    def page_versions(self, owner_id, page, page_size, search="", state=""):
        rows = []
        for definition in self.definitions.values():
            if definition.owner_id != owner_id:
                continue
            for version in self.versions(definition.id):
                name = version.name or definition.name
                if search.casefold() not in name.casefold() or (state and version.state != state):
                    continue
                rows.append(
                    {
                        "id": definition.id,
                        "version_id": version.id,
                        "name": name,
                        "number": version.number,
                        "description": version.description or definition.description,
                        "created_at": version.created_at.isoformat(),
                        "state": version.state.value,
                        "revision": version.revision,
                    }
                )
        rows.sort(key=lambda row: (row["created_at"], row["version_id"]), reverse=True)
        return rows[(page - 1) * page_size : page * page_size], len(rows)


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
                next_version_number=strategy.next_version_number,
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
                state=version.state.value,
                name=version.name,
                description=version.description,
                revision=version.revision,
            )
        )
        row = self.session.get(StrategyModel, version.strategy_id)
        if row is not None:
            row.current_version_id = version.id
            row.next_version_number = version.number + 1
        self.session.commit()

    def versions(self, strategy_id: str) -> tuple[StrategyVersion, ...]:
        rows = self.session.scalars(
            select(StrategyVersionModel)
            .where(StrategyVersionModel.strategy_id == strategy_id)
            .order_by(StrategyVersionModel.number)
        )
        return tuple(self._version(row) for row in rows)

    def get_version(self, version_id: str) -> StrategyVersion | None:
        row = self.session.get(StrategyVersionModel, version_id)
        return self._version(row) if row is not None else None

    @staticmethod
    def _version(row: StrategyVersionModel) -> StrategyVersion:
        return StrategyVersion(
            row.id,
            row.strategy_id,
            row.number,
            row.source_code,
            row.content_sha256,
            row.created_at,
            row.parent_version_id,
            StrategyState(row.state or "draft"),
            row.name or "",
            row.description or "",
            row.revision or 0,
        )

    def save_draft(self, version: StrategyVersion, expected_revision: int) -> None:
        result = self.session.execute(
            update(StrategyVersionModel)
            .where(
                StrategyVersionModel.id == version.id,
                StrategyVersionModel.state == StrategyState.DRAFT.value,
                StrategyVersionModel.revision == expected_revision,
            )
            .values(
                name=version.name,
                description=version.description,
                source_code=version.source_code,
                content_sha256=version.content_sha256,
                revision=version.revision,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            self.session.rollback()
            raise StateConflictError("策略已变化，请重新加载后编辑")
        self.session.commit()

    def advance_state(self, version_id: str, state: StrategyState) -> None:
        self.advance_state_in_transaction(self.session, version_id, state)
        self.session.commit()

    @staticmethod
    def advance_state_in_transaction(session, version_id, state):
        if state == StrategyState.DRAFT:
            return
        allowed = ["draft"] if state == StrategyState.TESTING else ["draft", "testing"]
        session.execute(
            update(StrategyVersionModel)
            .where(
                StrategyVersionModel.id == version_id,
                StrategyVersionModel.state.in_(allowed),
            )
            .values(state=state.value)
        )

    def page_versions(self, owner_id, page, page_size, search="", state=""):
        name = func.coalesce(func.nullif(StrategyVersionModel.name, ""), StrategyModel.name)
        query = (
            select(
                StrategyModel.id,
                StrategyVersionModel.id.label("version_id"),
                name.label("name"),
                StrategyVersionModel.number,
                StrategyVersionModel.description,
                StrategyVersionModel.created_at,
                StrategyVersionModel.state,
                StrategyVersionModel.revision,
            )
            .join(StrategyModel, StrategyVersionModel.strategy_id == StrategyModel.id)
            .where(
                StrategyModel.owner_id == owner_id,
            )
        )
        if search:
            query = query.where(name.contains(search, autoescape=True))
        if state:
            query = query.where(StrategyVersionModel.state == state)
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self.session.execute(
            query.order_by(
                StrategyVersionModel.created_at.desc(),
                StrategyVersionModel.id.desc(),
            )
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).mappings()
        return [{**row, "created_at": row["created_at"].isoformat()} for row in rows], total

    @staticmethod
    def _definition(row: StrategyModel) -> StrategyDefinition:
        return StrategyDefinition(
            row.id,
            row.owner_id,
            row.name,
            row.description,
            row.current_version_id,
            row.next_version_number or 1,
        )
