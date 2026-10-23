import json
from datetime import date, timedelta
from pathlib import Path

from easy_quant.application.ports.core import Clock
from easy_quant.domain.market_data.entities import AttemptStatus, RawEnvelope, SourceAttempt
from easy_quant.domain.market_data.indices import is_index


class FixtureIndexAcquisition:
    """v1 指数日线 fixture，只在离线端到端应用显式装配。"""

    def __init__(self, clock: Clock):
        self.clock = clock
        self.rows = json.loads(
            (Path(__file__).parents[1] / "fixtures/data_sources/index-daily-v1.json").read_text(
                encoding="utf-8"
            )
        )

    def acquire_with_attempts(self, request, *, force=False, source_keys=None):
        if not is_index(str(request.parameters["symbol"])):
            raise ValueError("离线指数 fixture 不支持股票同步")
        rows = [
            row
            for row in self.rows
            if request.parameters["start_date"] <= row["date"] <= request.parameters["end_date"]
        ]
        now = self.clock.now()
        return RawEnvelope(
            request.identity,
            "akshare",
            json.dumps(rows).encode(),
            "application/json",
            now,
            now + timedelta(hours=1),
        ), [SourceAttempt("akshare", 1, AttemptStatus.SUCCEEDED)]


class FixtureCalendarAcquisition:
    """v1 离线验收工作日日历，固定范围，不作为真实行情使用。"""

    def __init__(self, clock: Clock):
        self.clock = clock

    def acquire_with_attempts(self, request, *, force=False, source_keys=None):
        start = date(2025, 12, 1)
        rows = [
            {"trade_date": (start + timedelta(days=offset)).isoformat()}
            for offset in range(335)
            if (start + timedelta(days=offset)).weekday() < 5
        ]
        now = self.clock.now()
        return RawEnvelope(
            request.identity,
            "akshare",
            json.dumps(rows).encode(),
            "application/json",
            now,
            now + timedelta(hours=1),
        ), [SourceAttempt("akshare", 1, AttemptStatus.SUCCEEDED)]
