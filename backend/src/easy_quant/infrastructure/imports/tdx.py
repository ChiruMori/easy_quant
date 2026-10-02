from __future__ import annotations

import hashlib
import re
import struct
import zipfile
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import BinaryIO
from zoneinfo import ZoneInfo

import httpx

from easy_quant.domain.market_data.history import HistoryBar

ARCHIVE_URL = "https://data.tdx.com.cn/vipdoc/hsjday.zip"
FORMAT_VERSION = "tdx-day-v1"
RECORD = struct.Struct("<IIIIIfII")
PREFIXES = {
    "sh": ("600", "601", "603", "605", "688", "689"),
    "sz": ("000", "001", "002", "003", "300", "301", "302"),
    "bj": ("43", "83", "87", "88", "920"),
}


def stock_symbol(member: str) -> str | None:
    name = member.replace("\\", "/").split("/")[-1].lower()
    match = re.fullmatch(r"(sh|sz|bj)(\d{6})\.day", name)
    if match is None:
        return None
    market, symbol = match.groups()
    return symbol if symbol.startswith(PREFIXES[market]) else None


def parse_day(data: bytes, symbol: str) -> list[HistoryBar]:
    if len(data) % RECORD.size:
        raise ValueError("日线文件长度不是 32 字节的整数倍")
    bars: list[HistoryBar] = []
    previous: date | None = None
    for raw_day, opening, high, low, close, amount, volume, reserved in RECORD.iter_unpack(data):
        day = date(raw_day // 10000, raw_day // 100 % 100, raw_day % 100)
        if previous is not None and day <= previous:
            raise ValueError("日线日期重复或未递增")
        previous = day
        if reserved & 0xFFFFFF00 == 0xC3640000:
            volume = volume * 100 + (reserved & 0xFF)
        normalized_amount = Decimal(str(amount))
        if normalized_amount.is_finite() and normalized_amount >= 0:
            normalized_amount = normalized_amount.quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        bar = HistoryBar(
            symbol,
            day,
            Decimal(opening) / 100,
            Decimal(high) / 100,
            Decimal(low) / 100,
            Decimal(close) / 100,
            Decimal(volume),
            normalized_amount,
            datetime.combine(day, time(15), ZoneInfo("Asia/Shanghai")),
        )
        bar.validate()
        bars.append(bar)
    return bars


class TdxArchive:
    def __init__(self, archive: zipfile.ZipFile) -> None:
        self.archive = archive

    def members(self) -> list[tuple[str, str]]:
        members = []
        seen: set[str] = set()
        for entry in self.archive.infolist():
            symbol = stock_symbol(entry.filename)
            if symbol is None or entry.is_dir():
                continue
            if symbol in seen:
                raise ValueError(f"归档存在重复 A 股文件：{symbol}")
            if entry.file_size > 16 * 1024 * 1024:
                raise ValueError(f"单个日线文件过大：{symbol}")
            seen.add(symbol)
            members.append((entry.filename, symbol))
        return sorted(members)

    def read_bars(self, member: str, symbol: str) -> list[HistoryBar]:
        try:
            return parse_day(self.archive.read(member), symbol)
        except zipfile.BadZipFile as error:
            raise ValueError(f"ZIP 校验失败：{symbol}") from error


def sha256_stream(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def download_archive(client: httpx.Client, destination: Path) -> None:
    """流式下载到临时文件；完整收到且 ZIP 可读后再替换目标。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".zip.part")
    with client.stream("GET", ARCHIVE_URL) as response:
        response.raise_for_status()
        expected = response.headers.get("content-length")
        received = 0
        with temporary.open("wb") as output:
            for chunk in response.iter_bytes(1024 * 1024):
                output.write(chunk)
                received += len(chunk)
        if expected is not None and received != int(expected):
            raise ValueError("官方下载未完成，文件长度不匹配")
    with zipfile.ZipFile(temporary) as archive:
        if not TdxArchive(archive).members():
            raise ValueError("官方下载文件不包含 A 股日线")
    temporary.replace(destination)
