from __future__ import annotations

import io
import zipfile

from easy_quant.application.services.history_import import import_history
from easy_quant.infrastructure.imports.tdx import TdxArchive
from tests.infrastructure.test_tdx_archive import fixture_bytes


class Store:
    def __init__(self) -> None:
        self.stocks = set()
        self.rows = {}
        self.fail = True

    def completed(self, archive_sha256, symbol):
        return (archive_sha256, symbol) in self.stocks

    def write_stocks(self, archive_sha256, stocks, batch_size):
        symbol, bars = stocks[0]
        # 模拟第一批已写入，后续批次失败；完成标记只在成功结束时写入。
        self.rows[(symbol, bars[0].trading_day)] = bars[0]
        if self.fail:
            self.fail = False
            raise RuntimeError("模拟批次失败")
        for bar in bars:
            self.rows[(symbol, bar.trading_day)] = bar
        self.stocks.add((archive_sha256, symbol))


def test_partial_failure_replays_idempotently_and_then_skips_completed() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("sz000001.day", fixture_bytes())
    stream.seek(0)
    store = Store()
    with zipfile.ZipFile(stream) as archive:
        source = TdxArchive(archive)
        failed = import_history(source, store, "snapshot", batch_size=1)
        assert len(failed.failures) == 1 and not store.stocks
        assert len(store.rows) == 1
        complete = import_history(source, store, "snapshot", batch_size=1)
        assert complete.imported_rows == 2 and not complete.failures
        assert len(store.rows) == 2
        repeat = import_history(source, store, "snapshot")
        assert repeat.skipped_stocks == 1 and repeat.imported_rows == 0
        changed = import_history(source, store, "new-snapshot")
        assert changed.imported_stocks == 1 and len(store.rows) == 2


def test_invalid_stock_never_reaches_store() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("sz000001.day", b"bad")
    stream.seek(0)
    store = Store()
    with zipfile.ZipFile(stream) as archive:
        result = import_history(TdxArchive(archive), store, "snapshot")
    assert result.failures and not store.rows and not store.stocks
