from datetime import timedelta

import pytest

from easy_quant.application.services.identity_admin import IdentityAdminService
from easy_quant.domain.identity.entities import User, UserRole, UserStatus
from easy_quant.domain.shared.errors import ForbiddenError, StateConflictError
from easy_quant.infrastructure.persistence.repositories.in_memory_identity import (
    InMemoryIdentityRepository,
)
from tests.fakes.core import FixedClock, SequentialIdGenerator


def make_user(identifier, role, fixed_now):
    return User(identifier, identifier, "hash", role, UserStatus.ACTIVE, fixed_now)


def test_invitation_single_use_expiry_disable_and_admin_permissions(fixed_now) -> None:
    repository = InMemoryIdentityRepository()
    admin = make_user("admin", UserRole.ADMIN, fixed_now)
    repository.add_user(admin)
    clock = FixedClock(fixed_now)
    service = IdentityAdminService(repository, clock, SequentialIdGenerator())
    invitation, token = service.issue_invitation(admin, timedelta(hours=1))
    user = service.accept_invitation(token, "user", "very-secure-password")
    with pytest.raises(StateConflictError):
        service.accept_invitation(token, "other", "very-secure-password")
    service.set_status(admin, user.id, UserStatus.DISABLED)
    assert not user.is_active
    with pytest.raises(ForbiddenError):
        service.issue_invitation(user)


def test_expired_invitation_is_rejected(fixed_now) -> None:
    repository = InMemoryIdentityRepository()
    admin = make_user("admin", UserRole.ADMIN, fixed_now)
    repository.add_user(admin)
    clock = FixedClock(fixed_now)
    service = IdentityAdminService(repository, clock, SequentialIdGenerator())
    _, token = service.issue_invitation(admin, timedelta(seconds=1))
    clock.advance(timedelta(seconds=2))
    with pytest.raises(StateConflictError):
        service.accept_invitation(token, "user", "very-secure-password")
