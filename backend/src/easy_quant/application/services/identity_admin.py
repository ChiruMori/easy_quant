from __future__ import annotations

import secrets
from datetime import timedelta

from argon2 import PasswordHasher

from easy_quant.application.ports.core import Clock, IdGenerator
from easy_quant.application.ports.identity import IdentityRepository
from easy_quant.application.services.authentication import hash_token
from easy_quant.domain.identity.entities import Invitation, User, UserRole, UserStatus
from easy_quant.domain.shared.errors import ForbiddenError, NotFoundError


class IdentityAdminService:
    def __init__(self, repository: IdentityRepository, clock: Clock, ids: IdGenerator) -> None:
        self.repository, self.clock, self.ids = repository, clock, ids
        self.passwords = PasswordHasher()

    def issue_invitation(
        self, actor: User, lifetime: timedelta = timedelta(days=7)
    ) -> tuple[Invitation, str]:
        if actor.role is not UserRole.ADMIN:
            raise ForbiddenError()
        token = secrets.token_urlsafe(32)
        now = self.clock.now()
        invitation = Invitation(self.ids.new(), hash_token(token), actor.id, now + lifetime, now)
        self.repository.add_invitation(invitation)
        return invitation, token

    def accept_invitation(self, token: str, username: str, password: str) -> User:
        invitation = self.repository.get_invitation_by_hash(hash_token(token))
        if invitation is None:
            raise NotFoundError("invitation")
        user = User(
            self.ids.new(),
            username,
            self.passwords.hash(password),
            UserRole.USER,
            UserStatus.ACTIVE,
            self.clock.now(),
        )
        invitation.consume(user.id, self.clock.now())
        self.repository.add_user(user)
        return user

    def list_users(self, actor: User) -> tuple[User, ...]:
        if actor.role is not UserRole.ADMIN:
            raise ForbiddenError()
        return self.repository.list_users()

    def set_status(self, actor: User, user_id: str, status: UserStatus) -> User:
        if actor.role is not UserRole.ADMIN:
            raise ForbiddenError()
        user = self.repository.get_user(user_id)
        if user is None:
            raise NotFoundError("user")
        user.status = status
        self.repository.save_user(user)
        return user

    def set_role(self, actor: User, user_id: str, role: UserRole) -> User:
        if actor.role is not UserRole.ADMIN:
            raise ForbiddenError()
        user = self.repository.get_user(user_id)
        if user is None:
            raise NotFoundError("user")
        user.role = role
        self.repository.save_user(user)
        return user
