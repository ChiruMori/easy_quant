from easy_quant.application.services.imports import ImportService
from easy_quant.infrastructure.imports.csv_reader import CsvUploadReader


class Records:
    def __init__(self):
        self.rows = {}

    def upsert_many(self, dataset_key, rows):
        for row in rows:
            self.rows[(row["symbol"], row["trading_day"])] = row
        return len(tuple(rows))


def test_preview_and_atomic_confirmation() -> None:
    records = Records()
    service = ImportService(CsvUploadReader(), records)
    preview = service.preview_daily_bars(
        b"symbol,trading_day,open,high,low,close,volume\n000001,2026-09-28,10,11,9,10.5,1000\n"
    )
    assert preview.valid
    assert service.confirm("daily-bars", preview) == 1


def test_invalid_rows_are_not_imported() -> None:
    records = Records()
    preview = ImportService(CsvUploadReader(), records).preview_daily_bars(
        b"symbol,trading_day,open\n000001,2026-09-28,x\n"
    )
    assert not preview.valid
    assert records.rows == {}
