"""只重做明确幂等的完整数据库操作，绝不重做外部HTTP请求。"""

import logging
import traceback
from functools import wraps

from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from easy_quant.application.ports.storage_errors import StorageFailure

logger = logging.getLogger(__name__)
DISCONNECTS = {2006, 2013, 2055}
TRANSACTION_RETRY = {1205, 1213}


def database_code(error):
    if isinstance(error, StorageFailure):
        return error.details.get("database_code")
    original = getattr(error, "orig", None)
    arguments = getattr(original, "args", ())
    return arguments[0] if arguments and isinstance(arguments[0], int) else None


def storage_failure(error, operation):
    number = database_code(error)
    if number in {1044, 1045, 1049, 1142, 1143}:
        code, message = "database_configuration", "数据库连接配置、权限或库名错误，请检查配置"
    elif number in {1054, 1146}:
        code, message = "database_schema", "数据库表或字段不匹配，请检查数据库迁移"
    elif number in DISCONNECTS:
        code, message = (
            "database_connection_lost",
            "数据库连接丢失或查询超时，请检查数据库服务与网络",
        )
    elif number in {2002, 2003, 2005}:
        code, message = "database_unavailable", "无法连接数据库，请检查地址、网络和数据库服务"
    elif number in TRANSACTION_RETRY:
        code, message = "database_transaction", "数据库锁等待超时或死锁，请检查事务与锁日志"
    else:
        code, message = "database_failed", "数据库操作失败，请检查后台数据库错误日志"
    return StorageFailure(code, message, {"database_code": number, "operation": operation})


def log_database_error(log, error, operation, **context):
    # 不使用异常repr/str/format_exception，避免DBAPI错误中包含SQL、绑定参数或凭据。
    frames = []
    current, seen = error, set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        frames.append(
            type(current).__name__ + "\n" + "".join(traceback.format_tb(current.__traceback__))
        )
        current = current.__cause__ or (
            current.__context__ if not current.__suppress_context__ else None
        )
    log.error(
        "数据库操作失败 operation=%s database_code=%s context=%s\n%s",
        operation,
        database_code(error),
        context,
        "\n".join(frames),
    )


def run_idempotent(session, operation, action):
    for attempt in range(2):
        try:
            result = action()
            if attempt:
                logger.info("数据库局部恢复成功 operation=%s", operation)
            return result
        except SQLAlchemyError as error:
            number = database_code(error)
            recoverable = number in DISCONNECTS | TRANSACTION_RETRY
            try:
                if number in DISCONNECTS or (
                    isinstance(error, DBAPIError) and error.connection_invalidated
                ):
                    session.invalidate()
                else:
                    session.rollback()
            except Exception:
                log_database_error(logger, error, operation, cleanup_failed=True)
                raise storage_failure(error, operation) from error
            if attempt == 0 and recoverable:
                logger.warning(
                    "数据库局部恢复 operation=%s database_code=%s action=%s attempt=1/1",
                    operation,
                    number,
                    "invalidate" if number in DISCONNECTS else "rollback",
                )
                continue
            log_database_error(logger, error, operation)
            raise storage_failure(error, operation) from error


def idempotent_operation(operation):
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            return run_idempotent(self.session, operation, lambda: method(self, *args, **kwargs))

        return wrapped

    return decorate
