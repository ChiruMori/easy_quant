from __future__ import annotations

from easy_quant.domain.identity.entities import Invitation, User, UserSession


class InMemoryIdentityRepository:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.invitations: dict[str, Invitation] = {}
        self.sessions: dict[str, UserSession] = {}

    def has_any_user(self) -> bool:
        return bool(self.users)

    def add_user(self, user: User) -> None:
        if any(item.username == user.username for item in self.users.values()):
            raise ValueError("用户名已存在")
        self.users[user.id] = user

    def get_user(self, user_id: str) -> User | None:
        return self.users.get(user_id)

    def get_user_by_username(self, username: str) -> User | None:
        return next((item for item in self.users.values() if item.username == username), None)

    def add_invitation(self, invitation: Invitation) -> None:
        self.invitations[invitation.token_hash] = invitation

    def get_invitation_by_hash(self, token_hash: str) -> Invitation | None:
        return self.invitations.get(token_hash)

    def add_session(self, session: UserSession) -> None:
        self.sessions[session.token_hash] = session

    def get_session_by_hash(self, token_hash: str) -> UserSession | None:
        return self.sessions.get(token_hash)

    def save_session(self, session: UserSession) -> None:
        self.sessions[session.token_hash] = session

    def list_users(self) -> tuple[User, ...]:
        return tuple(self.users.values())

    def save_user(self, user: User) -> None:
        self.users[user.id] = user

    def list_invitations(self) -> tuple[Invitation, ...]:
        return tuple(self.invitations.values())
