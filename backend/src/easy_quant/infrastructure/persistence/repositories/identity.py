from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from easy_quant.domain.identity.entities import Invitation, User, UserRole, UserSession, UserStatus
from easy_quant.infrastructure.persistence.models.identity import (
    InvitationModel,
    SessionModel,
    UserModel,
)


class SqlAlchemyIdentityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def has_any_user(self) -> bool:
        return bool(self.session.scalar(select(func.count()).select_from(UserModel)))

    def add_user(self, user: User) -> None:
        self.session.add(
            UserModel(
                id=user.id,
                username=user.username,
                password_hash=user.password_hash,
                role=user.role.value,
                status=user.status.value,
                created_at=user.created_at,
            )
        )
        self.session.commit()

    def get_user(self, user_id: str) -> User | None:
        return self._to_user(self.session.get(UserModel, user_id))

    def get_user_by_username(self, username: str) -> User | None:
        return self._to_user(
            self.session.scalar(select(UserModel).where(UserModel.username == username))
        )

    def add_invitation(self, invitation: Invitation) -> None:
        self.session.add(
            InvitationModel(
                id=invitation.id,
                token_hash=invitation.token_hash,
                issued_by_user_id=invitation.issued_by_user_id,
                created_at=invitation.created_at,
                expires_at=invitation.expires_at,
                used_at=invitation.used_at,
                revoked_at=invitation.revoked_at,
            )
        )
        self.session.commit()

    def get_invitation_by_hash(self, token_hash: str) -> Invitation | None:
        row = self.session.scalar(
            select(InvitationModel).where(InvitationModel.token_hash == token_hash)
        )
        return None if row is None else self._to_invitation(row)

    def add_session(self, session: UserSession) -> None:
        self.session.add(
            SessionModel(
                id=session.id,
                user_id=session.user_id,
                token_hash=session.token_hash,
                csrf_token_hash=session.csrf_token_hash,
                created_at=session.created_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
            )
        )
        self.session.commit()

    def get_session_by_hash(self, token_hash: str) -> UserSession | None:
        row = self.session.scalar(select(SessionModel).where(SessionModel.token_hash == token_hash))
        return None if row is None else self._to_session(row)

    def save_session(self, session: UserSession) -> None:
        row = self.session.get(SessionModel, session.id)
        if row is not None:
            row.revoked_at = session.revoked_at
            self.session.commit()

    def list_users(self) -> tuple[User, ...]:
        users: list[User] = []
        for row in self.session.scalars(select(UserModel)):
            user = self._to_user(row)
            if user is not None:
                users.append(user)
        return tuple(users)

    def save_user(self, user: User) -> None:
        row = self.session.get(UserModel, user.id)
        if row is not None:
            row.role = user.role.value
            row.status = user.status.value
            self.session.commit()

    def list_invitations(self) -> tuple[Invitation, ...]:
        return tuple(
            self._to_invitation(row) for row in self.session.scalars(select(InvitationModel))
        )

    @staticmethod
    def _to_user(row: UserModel | None) -> User | None:
        if row is None:
            return None
        return User(
            id=row.id,
            username=row.username,
            password_hash=row.password_hash,
            role=UserRole(row.role),
            status=UserStatus(row.status),
            created_at=row.created_at,
        )

    @staticmethod
    def _to_invitation(row: InvitationModel) -> Invitation:
        return Invitation(
            id=row.id,
            token_hash=row.token_hash,
            issued_by_user_id=row.issued_by_user_id,
            expires_at=row.expires_at,
            created_at=row.created_at,
            used_at=row.used_at,
            used_by_user_id=row.used_by_user_id,
            revoked_at=row.revoked_at,
        )

    @staticmethod
    def _to_session(row: SessionModel) -> UserSession:
        return UserSession(
            id=row.id,
            user_id=row.user_id,
            token_hash=row.token_hash,
            csrf_token_hash=row.csrf_token_hash,
            expires_at=row.expires_at,
            created_at=row.created_at,
            revoked_at=row.revoked_at,
        )
