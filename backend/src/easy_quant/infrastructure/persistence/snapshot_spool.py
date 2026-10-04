from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Iterator
from typing import Any


class SnapshotSpool:
    """按行编码快照，内存上限固定，超出后落到系统临时文件。"""

    def __init__(self) -> None:
        self._file = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)  # noqa: SIM115
        self._digest = hashlib.sha256()
        self.record_count = 0
        self._closed = False
        self._write(b"[")

    def _write(self, chunk: bytes) -> None:
        self._file.write(chunk)
        self._digest.update(chunk)

    def append(self, row: dict[str, Any]) -> None:
        if self._closed:
            raise RuntimeError("快照已经结束")
        if self.record_count:
            self._write(b", ")
        self._write(json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        self.record_count += 1

    def finish(self) -> str:
        if not self._closed:
            self._write(b"]")
            self._closed = True
        return self._digest.hexdigest()

    def chunks(self, size: int = 64 * 1024) -> Iterator[bytes]:
        if not self._closed:
            raise RuntimeError("快照尚未结束")
        self._file.seek(0)
        while chunk := self._file.read(size):
            yield chunk

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> SnapshotSpool:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
