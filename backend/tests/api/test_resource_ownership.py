import pytest

from easy_quant.application.authorization import require_owner
from easy_quant.domain.identity.entities import User, UserRole, UserStatus
from easy_quant.domain.shared.errors import ForbiddenError


@pytest.mark.parametrize("resource", ["strategy", "backtest", "live", "notification", "job"])
def test_private_resources_reject_other_users(resource, fixed_now) -> None:
    user = User("u1", "one", "hash", UserRole.USER, UserStatus.ACTIVE, fixed_now)
    with pytest.raises(ForbiddenError):
        require_owner(user, f"other-{resource}")
    require_owner(user, "u1")
