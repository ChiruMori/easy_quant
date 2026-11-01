"""采集任务的请求预算；客户端逐次请求调用，包含分页和重试。"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


class CollectionCancelled(BaseException):
    """不能被来源的普通失败重试捕获。"""


@dataclass
class RequestBudget:
    clock: Any
    sleeper: Any
    check: Any
    interval: float = 5.0
    last: Any = None

    def before_request(self):
        self.check()
        if self.last is not None:
            remaining = self.interval - (self.clock.now() - self.last).total_seconds()
            while remaining > 0:
                self.sleeper.sleep(min(remaining, 1.0))
                self.check()
                remaining = self.interval - (self.clock.now() - self.last).total_seconds()
        self.last = self.clock.now()


_current: ContextVar[Any] = ContextVar("collection_request_budget", default=None)


def before_data_request(_request=None):
    budget = _current.get()
    if budget is not None:
        budget.before_request()


@contextmanager
def request_budget(budget):
    token = _current.set(budget)
    try:
        yield
    finally:
        _current.reset(token)
