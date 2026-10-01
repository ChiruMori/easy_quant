from easy_quant.domain.identity.entities import User, UserRole
from easy_quant.domain.shared.errors import ForbiddenError


def require_owner(user: User, owner_id: str) -> None:
    if user.role is not UserRole.ADMIN and user.id != owner_id:
        raise ForbiddenError()
