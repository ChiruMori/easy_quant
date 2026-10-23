from __future__ import annotations

import codecs
import hashlib
import json
import zlib
from collections.abc import Iterable
from decimal import Decimal

from easy_quant.domain.shared.errors import StateConflictError


def snapshot_prices(chunks: Iterable[bytes], snapshot_id: str, day: str, symbols: set[str]):
    """扫描旧快照，只保留指定日的目标价格，不把完整快照装入内存。"""
    inflate = zlib.decompressobj(wbits=31)
    utf8 = codecs.getincrementaldecoder("utf-8")()
    digest = hashlib.sha256()
    decoder = json.JSONDecoder()
    buffer = ""
    prices: dict[str, Decimal] = {}
    started = finished = seen = False

    def consume(payload: bytes, *, final: bool = False):
        nonlocal buffer, started, finished
        digest.update(payload)
        buffer += utf8.decode(payload, final=final)
        buffer = buffer.lstrip()
        if not started:
            if not buffer:
                return
            if not buffer.startswith("["):
                raise ValueError("invalid snapshot")
            buffer = buffer[1:]
            started = True
        cursor = 0
        while not finished:
            while cursor < len(buffer) and buffer[cursor] in " \r\n\t,":
                cursor += 1
            if cursor < len(buffer) and buffer[cursor] == "]":
                finished = True
                cursor += 1
                break
            try:
                row, end = decoder.raw_decode(buffer, cursor)
            except json.JSONDecodeError:
                break
            cursor = end
            if not isinstance(row, dict):
                raise ValueError("invalid snapshot record")
            symbol = str(row.get("symbol", ""))
            if symbol in symbols and str(row.get("trading_day")) == day:
                prices[symbol] = Decimal(str(row["close"]))
        buffer = buffer[cursor:]

    try:
        for chunk in chunks:
            seen = True
            consume(inflate.decompress(chunk))
        if not seen:
            return {}
        consume(inflate.flush(), final=True)
        if not inflate.eof or not finished or buffer.strip() or digest.hexdigest() != snapshot_id:
            raise ValueError("invalid snapshot")
    except (ValueError, KeyError, zlib.error) as error:
        raise StateConflictError("原回测快照损坏，无法重建股票收益") from error
    return prices
