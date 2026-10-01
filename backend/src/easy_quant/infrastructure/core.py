from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import uuid4


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SystemSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class UuidGenerator:
    def new(self) -> str:
        return str(uuid4())
