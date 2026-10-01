from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping


class CsvUploadReader:
    def rows(self, content: bytes) -> Iterable[Mapping[str, object]]:
        text = content.decode("utf-8-sig")
        yield from csv.DictReader(io.StringIO(text))
