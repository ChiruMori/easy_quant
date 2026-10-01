from easy_quant.domain.shared.errors import DomainError


class ApplicationError(DomainError):
    """应用层可安全返回给调用方的错误。"""


class AuthenticationRequired(ApplicationError):
    def __init__(self) -> None:
        super().__init__("authentication_required", "请先登录")


class InvalidCredentials(ApplicationError):
    def __init__(self) -> None:
        super().__init__("invalid_credentials", "用户名或密码错误")
