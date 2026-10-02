from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from easy_quant.domain.market_data.history import HistoryBar
from easy_quant.domain.shared.errors import DomainError


class HistoryArchive(Protocol):
    def members(self) -> Sequence[tuple[str, str]]: ...

    def read_bars(self, member: str, symbol: str) -> list[HistoryBar]: ...


class HistoryStore(Protocol):
    def completed(self, archive_sha256: str, symbol: str) -> bool: ...

    def write_stocks(
        self, archive_sha256: str, stocks: list[tuple[str, list[HistoryBar]]], batch_size: int
    ) -> None: ...


@dataclass
class HistoryImportResult:
    stock_files: int = 0
    imported_stocks: int = 0
    skipped_stocks: int = 0
    imported_rows: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)


def import_history(
    archive: HistoryArchive,
    store: HistoryStore,
    archive_sha256: str,
    *,
    batch_size: int = 2000,
    progress: Callable[[HistoryImportResult], None] = lambda _result: None,
) -> HistoryImportResult:
    if not 1 <= batch_size <= 10000:
        raise ValueError("批次大小必须在 1 到 10000 之间")
    result = HistoryImportResult()
    members = archive.members()
    result.stock_files = len(members)
    if not members:
        raise ValueError("归档中没有 A 股日线文件")
    pending: list[tuple[str, list[HistoryBar]]] = []
    pending_rows = 0

    def flush() -> None:
        nonlocal pending_rows
        if not pending:
            return
        try:
            store.write_stocks(archive_sha256, pending, batch_size)
            result.imported_stocks += len(pending)
            result.imported_rows += pending_rows
        except (ValueError, RuntimeError, DomainError) as error:
            result.failures.extend(
                {"symbol": symbol, "reason": str(error)} for symbol, _bars in pending
            )
        pending.clear()
        pending_rows = 0
        progress(result)

    for member, symbol in members:
        if store.completed(archive_sha256, symbol):
            result.skipped_stocks += 1
        else:
            try:
                bars = archive.read_bars(member, symbol)
                if not bars:
                    raise ValueError("日线文件为空")
                for bar in bars:
                    bar.validate()
                pending.append((symbol, bars))
                pending_rows += len(bars)
            except (ValueError, RuntimeError, DomainError) as error:
                result.failures.append({"member": member, "symbol": symbol, "reason": str(error)})
        if pending_rows >= 100000 or len(pending) >= 50:
            flush()
    flush()
    progress(result)
    return result
