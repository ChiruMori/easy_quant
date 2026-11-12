"""数据库边界向应用报告的脱敏错误，不包含SQL、参数或连接串。"""

from easy_quant.domain.shared.errors import DomainError


class StorageFailure(DomainError):
    def __init__(self, code, message, details=None):
        super().__init__(code, message, details or {})
