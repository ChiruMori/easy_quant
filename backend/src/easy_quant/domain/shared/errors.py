from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(eq=False)
class DomainError(Exception):
    code: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


class ValidationError(DomainError):
    def __init__(self, message: str, details: Mapping[str, object] | None = None) -> None:
        super().__init__("validation_error", message, details or {})


class StateConflictError(DomainError):
    def __init__(self, message: str, details: Mapping[str, object] | None = None) -> None:
        super().__init__("state_conflict", message, details or {})


class NotFoundError(DomainError):
    def __init__(self, resource: str) -> None:
        super().__init__("not_found", "资源不存在", {"resource": resource})


class ForbiddenError(DomainError):
    def __init__(self) -> None:
        super().__init__("forbidden", "无权执行此操作")
