from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from easy_quant.domain.shared.errors import StateConflictError
from easy_quant.domain.shared.value_objects import ensure_utc


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(slots=True)
class User:
    id: str
    username: str
    password_hash: str
    role: UserRole
    status: UserStatus
    created_at: datetime

    def __post_init__(self) -> None:
        self.username = self.username.strip().casefold()
        self.created_at = ensure_utc(self.created_at)

    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.ACTIVE


@dataclass(slots=True)
class Invitation:
    id: str
    token_hash: str
    issued_by_user_id: str
    expires_at: datetime
    created_at: datetime
    used_at: datetime | None = None
    used_by_user_id: str | None = None
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        self.expires_at = ensure_utc(self.expires_at)
        self.created_at = ensure_utc(self.created_at)

    def consume(self, user_id: str, now: datetime) -> None:
        now = ensure_utc(now)
        if self.revoked_at is not None or self.used_at is not None or now >= self.expires_at:
            raise StateConflictError("邀请码无效或已过期")
        self.used_at = now
        self.used_by_user_id = user_id


@dataclass(slots=True)
class UserSession:
    id: str
    user_id: str
    token_hash: str
    csrf_token_hash: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        self.expires_at = ensure_utc(self.expires_at)
        self.created_at = ensure_utc(self.created_at)

    def is_valid(self, now: datetime) -> bool:
        return self.revoked_at is None and ensure_utc(now) < self.expires_at
