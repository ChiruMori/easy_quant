from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from easy_quant.application.ports.market_data import NormalizedRecordRepository, UploadReader

REQUIRED_DAILY_BAR_FIELDS = {"symbol", "trading_day", "open", "high", "low", "close", "volume"}


@dataclass(frozen=True, slots=True)
class ImportIssue:
    row: int
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class ImportPreview:
    rows: tuple[dict[str, object], ...]
    issues: tuple[ImportIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


class ImportService:
    def __init__(self, reader: UploadReader, repository: NormalizedRecordRepository) -> None:
        self.reader = reader
        self.repository = repository

    def preview_daily_bars(self, content: bytes) -> ImportPreview:
        accepted: list[dict[str, object]] = []
        issues: list[ImportIssue] = []
        for number, raw in enumerate(self.reader.rows(content), start=2):
            missing = REQUIRED_DAILY_BAR_FIELDS - raw.keys()
            for field in sorted(missing):
                issues.append(ImportIssue(number, field, "缺少必填字段"))
            try:
                row = dict(raw)
                for field in ("open", "high", "low", "close", "volume"):
                    row[field] = Decimal(str(raw[field]))
                accepted.append(row)
            except (KeyError, InvalidOperation):
                issues.append(ImportIssue(number, "price", "数值格式无效"))
        return ImportPreview(tuple(accepted), tuple(issues))

    def confirm(self, dataset_key: str, preview: ImportPreview) -> int:
        if not preview.valid:
            raise ValueError("预检存在错误，不允许部分导入")
        return self.repository.upsert_many(dataset_key, preview.rows)
