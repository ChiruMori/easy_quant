import json
from datetime import timedelta
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
