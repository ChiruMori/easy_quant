import pytest

from easy_quant.domain.shared.errors import ValidationError
from easy_quant.infrastructure.security import SecretBox, bounded_page_size


def test_secret_box_encrypts_and_detects_tampering() -> None:
    box = SecretBox("test-only-master-secret")
    encrypted = box.encrypt("mail@example.test")
    assert "mail@example.test" not in encrypted
    assert box.decrypt(encrypted) == "mail@example.test"
    with pytest.raises(ValidationError):
        box.decrypt(encrypted[:-2] + "xx")


@pytest.mark.parametrize(("value", "expected"), [(None, 50), (0, 1), (999, 200), ("bad", 50)])
def test_page_size_is_bounded(value, expected) -> None:
    assert bounded_page_size(value) == expected
