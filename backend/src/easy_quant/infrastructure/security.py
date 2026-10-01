from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from easy_quant.domain.shared.errors import ValidationError


class SecretBox:
    """Encrypt small credentials before persistence with authenticated encryption."""

    def __init__(self, secret: str) -> None:
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            raise ValidationError("敏感配置不能为空")
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise ValidationError("敏感配置无法解密") from exc


def bounded_page_size(value: int | str | None, *, default: int = 50, maximum: int = 200) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))
