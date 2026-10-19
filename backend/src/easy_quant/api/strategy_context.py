from typing import Any


def strategy_context(container: Any, owner_id: str, version_id: str) -> dict[str, object] | None:
    repository = container.state.strategies
    for definition in repository.definitions.values():
        if definition.owner_id != owner_id:
            continue
        for version in repository.versions(definition.id):
            if version.id == version_id:
                return {
                    "id": definition.id,
                    "name": version.name or definition.name,
                    "description": version.description or definition.description,
                    "version_id": version.id,
                    "number": version.number,
                    "source_code": version.source_code,
                }
    return None
