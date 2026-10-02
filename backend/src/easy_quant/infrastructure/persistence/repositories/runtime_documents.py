from __future__ import annotations

import json
from collections.abc import Iterator, MutableMapping
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from easy_quant.infrastructure.persistence.models.runtime_state import RuntimeDocumentModel


class SqlJsonDict(MutableMapping[str, dict[str, Any]]):
    def __init__(self, session: Session, namespace: str, *, commit_on_write: bool = True) -> None:
        self.session, self.namespace = session, namespace
        self.commit_on_write = commit_on_write

    def _write(self) -> None:
        if self.commit_on_write:
            self.session.commit()
        else:
            self.session.flush()

    def __getitem__(self, key: str) -> dict[str, Any]:
        row = self.session.get(RuntimeDocumentModel, (self.namespace, key))
        if row is None:
            raise KeyError(key)
        return json.loads(row.payload_json)

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        self.session.merge(
            RuntimeDocumentModel(
                namespace=self.namespace,
                key=key,
                payload_json=json.dumps(value, ensure_ascii=False, default=str),
            )
        )
        self._write()

    def __delitem__(self, key: str) -> None:
        self.session.execute(
            delete(RuntimeDocumentModel).where(
                RuntimeDocumentModel.namespace == self.namespace,
                RuntimeDocumentModel.key == key,
            )
        )
        self._write()

    def __iter__(self) -> Iterator[str]:
        return iter(
            self.session.scalars(
                select(RuntimeDocumentModel.key).where(
                    RuntimeDocumentModel.namespace == self.namespace
                )
            ).all()
        )

    def __len__(self) -> int:
        return len(list(iter(self)))


class SqlJsonList:
    """小规模受限部署使用的持久 JSON 列表。"""

    def __init__(self, session: Session, namespace: str, *, commit_on_write: bool = True) -> None:
        self._mapping = SqlJsonDict(session, namespace, commit_on_write=commit_on_write)

    def _keys(self) -> list[str]:
        return sorted(self._mapping)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self._mapping[self._keys()[index]]

    def __setitem__(self, index: int, value: dict[str, Any]) -> None:
        key = self._keys()[index]
        self._mapping[key] = value

    def __delitem__(self, index: int) -> None:
        del self._mapping[self._keys()[index]]

    def __len__(self) -> int:
        return len(self._mapping)

    def insert(self, index: int, value: dict[str, Any]) -> None:
        key = str(value.get("id") or f"{index:08d}")
        self._mapping[key] = value

    def append(self, value: dict[str, Any]) -> None:
        self.insert(len(self), value)
