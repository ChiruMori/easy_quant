from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from easy_quant.application.errors import AuthenticationRequired, InvalidCredentials
from easy_quant.application.ports.core import Clock, IdGenerator
from easy_quant.application.ports.identity import IdentityRepository
from easy_quant.domain.identity.entities import User, UserRole, UserSession, UserStatus
from easy_quant.domain.shared.errors import StateConflictError, ValidationError


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SessionCredentials:
    token: str
    csrf_token: str
    expires_at: datetime


class AuthenticationService:
    def __init__(
        self,
        repository: IdentityRepository,
        clock: Clock,
        ids: IdGenerator,
        password_hasher: PasswordHasher | None = None,
        session_lifetime: timedelta = timedelta(hours=12),
    ) -> None:
        self.repository = repository
        self.clock = clock
        self.ids = ids
        self.password_hasher = password_hasher or PasswordHasher()
        self.session_lifetime = session_lifetime

    def initialize_admin(self, username: str, password: str) -> User:
        if self.repository.has_any_user():
            raise StateConflictError("系统已经完成初始化")
        self._validate_password(password)
        user = User(
            id=self.ids.new(),
            username=username,
            password_hash=self.password_hasher.hash(password),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            created_at=self.clock.now(),
        )
        if not user.username:
            raise ValidationError("用户名不能为空")
        self.repository.add_user(user)
        return user

    def login(self, username: str, password: str) -> tuple[User, SessionCredentials]:
        user = self.repository.get_user_by_username(username.strip().casefold())
        if user is None or not user.is_active:
            raise InvalidCredentials()
        try:
            self.password_hasher.verify(user.password_hash, password)
        except VerifyMismatchError as exc:
            raise InvalidCredentials() from exc
        return user, self._create_session(user.id)

    def authenticate(self, token: str | None) -> tuple[User, UserSession]:
        if not token:
            raise AuthenticationRequired()
        session = self.repository.get_session_by_hash(hash_token(token))
        if session is None or not session.is_valid(self.clock.now()):
            raise AuthenticationRequired()
        user = self.repository.get_user(session.user_id)
        if user is None or not user.is_active:
            raise AuthenticationRequired()
        return user, session

    def logout(self, token: str | None) -> None:
        if not token:
            return
        session = self.repository.get_session_by_hash(hash_token(token))
        if session is not None and session.revoked_at is None:
            session.revoked_at = self.clock.now()
            self.repository.save_session(session)

    def check_csrf(self, session: UserSession, csrf_token: str | None) -> None:
        if not csrf_token or not secrets.compare_digest(
            session.csrf_token_hash, hash_token(csrf_token)
        ):
            raise ValidationError("CSRF token 无效")

    def _create_session(self, user_id: str) -> SessionCredentials:
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(24)
        now = self.clock.now()
        expires_at = now + self.session_lifetime
        session = UserSession(
            id=self.ids.new(),
            user_id=user_id,
            token_hash=hash_token(token),
            csrf_token_hash=hash_token(csrf_token),
            created_at=now,
            expires_at=expires_at,
        )
        self.repository.add_session(session)
        return SessionCredentials(token, csrf_token, expires_at)

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 8:
            raise ValidationError("密码至少需要 8 个字符")
