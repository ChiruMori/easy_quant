"""COD/MD1 布局改编自 jing2uo/tdx2db，MIT 声明见根 THIRD_PARTY_NOTICES.md。"""

from __future__ import annotations

import hashlib
import io
import math
import re
import struct
import zipfile
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import httpx

from easy_quant.application.services.tdx_incremental import DailyArchive, HolidayCalendar
from easy_quant.infrastructure.imports.tdx import RECORD, parse_day, stock_symbol

DAILY_URL = "https://www.tdx.com.cn/products/data/data/g4day/{day}.zip"
CALENDAR_URL = "https://www.tdx.com.cn/products/data/data/dbf/gbbq.zip"
FORMAT_VERSION = "tdx-md1-v1"


def _read(archive: zipfile.ZipFile, name: str, limit: int) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > limit:
        raise ValueError("官方 ZIP 成员超过大小限制")
    return archive.read(info)


def parse_daily(payload: bytes, day: date) -> DailyArchive:
    bars = []
    seen: set[str] = set()
    suspended = 0
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        expected = {
            f"{market}{day:%y%m%d}.{suffix}"
            for market in ("sh", "sz", "bj")
            for suffix in ("cod", "md1")
        }
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != expected:
            raise ValueError("单日 ZIP 必须包含同日沪深京唯一 COD/MD1 配对")
        for market in ("sh", "sz", "bj"):
            cod = _read(archive, f"{market}{day:%y%m%d}.cod", 8 * 1024 * 1024)
            md1 = _read(archive, f"{market}{day:%y%m%d}.md1", 32 * 1024 * 1024)
            if not cod or len(cod) % 150 or not md1 or len(md1) % 512:
                raise ValueError("COD/MD1 文件长度无效")
            for offset in range(0, len(cod), 150):
                raw_code = cod[offset : offset + 6]
                try:
                    symbol = raw_code.decode("ascii").rstrip("\x00 ")
                except UnicodeDecodeError:
                    raise ValueError("COD 股票代码不是 ASCII") from None
                if stock_symbol(f"{market}{symbol}.day") is None:
                    continue
                if symbol in seen:
                    raise ValueError("增量包存在重复 A 股代码")
                seen.add(symbol)
                sequence = struct.unpack_from("<H", cod, offset + 32)[0]
                position = sequence * 512
                if position + 512 > len(md1):
                    raise ValueError("COD 引用超出 MD1 行情范围")
                prices = struct.unpack_from("<dddd", md1, position + 12)
                volume = struct.unpack_from("<Q", md1, position + 56)[0]
                amount = struct.unpack_from("<d", md1, position + 72)[0]
                if not all(math.isfinite(value) and value >= 0 for value in (*prices, amount)):
                    raise ValueError("MD1 存在非有限或负数行情")
                if volume == 0 and amount == 0:
                    suspended += 1
                    continue
                if any(value <= 0 for value in prices):
                    raise ValueError("成交行情价格必须为正")
                cents = [
                    int((Decimal(str(value)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                    for value in prices
                ]
                raw_volume = volume if volume <= 0xFFFFFFFF else volume // 100
                reserved = 0 if volume <= 0xFFFFFFFF else 0xC3640000 | volume % 100
                if max(cents) > 0xFFFFFFFF or raw_volume > 0xFFFFFFFF:
                    raise ValueError("MD1 超出 DAY 兼容数值范围")
                try:
                    record = RECORD.pack(
                        int(day.strftime("%Y%m%d")), *cents, amount, raw_volume, reserved
                    )
                except (OverflowError, struct.error):
                    raise ValueError("MD1 成交额超出 DAY 兼容范围") from None
                bars.extend(parse_day(record, symbol))
    if not bars:
        raise ValueError("单日包没有有效 A 股行情")
    return DailyArchive(day, hashlib.sha256(payload).hexdigest(), tuple(bars), suspended)


def parse_calendar(payload: bytes) -> HolidayCalendar:
    with zipfile.ZipFile(io.BytesIO(payload)) as outer:
        nested = _read(outer, "zhb.zip", 4 * 1024 * 1024)
    with zipfile.ZipFile(io.BytesIO(nested)) as inner:
        content = _read(inner, "needini.dat", 1024 * 1024).decode("gb18030")
    years: set[int] = set()
    holidays: set[date] = set()
    for line in content.splitlines():
        if not re.match(r"^Y\d+=", line.strip()):
            continue
        values = [
            value.strip() for value in line.strip().split("=", 1)[1].split(",") if value.strip()
        ]
        if not values or not re.fullmatch(r"\d{4}", values[0]):
            raise ValueError("官方休市年度格式无效")
        year = int(values[0])
        if year in years:
            raise ValueError("官方休市年度重复")
        years.add(year)
        for value in values[1:]:
            if not re.fullmatch(r"\d{4}", value):
                raise ValueError("官方休市日期格式无效")
            holidays.add(date(year, int(value[:2]), int(value[2:])))
    if not years:
        raise ValueError("官方休市日历没有年度声明")
    return HolidayCalendar(
        frozenset(years), frozenset(holidays), hashlib.sha256(payload).hexdigest()
    )


class OfficialDailyFeed:
    def __init__(self, client: httpx.Client, directory: Path) -> None:
        self.client, self.directory = client, directory

    def _download(self, url: str) -> bytes | None:
        try:
            with self.client.stream("GET", url) as response:
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes(65536):
                    content.extend(chunk)
                    if len(content) > 16 * 1024 * 1024:
                        raise ValueError("官方增量下载超过 16 MiB 限制")
                size = response.headers.get("content-length")
                if size is not None and len(content) != int(size):
                    raise ValueError("官方增量下载长度不匹配")
                return bytes(content)
        except httpx.HTTPError as error:
            raise RuntimeError(f"官方增量下载失败（{type(error).__name__}）") from None

    def _save(self, name: str, payload: bytes) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / name
        temporary = target.with_suffix(".zip.part")
        temporary.write_bytes(payload)
        temporary.replace(target)

    def calendar(self) -> HolidayCalendar:
        payload = self._download(CALENDAR_URL)
        if payload is None:
            raise RuntimeError("官方休市日历暂不可用")
        try:
            calendar = parse_calendar(payload)
        except (ValueError, KeyError, UnicodeError, zipfile.BadZipFile):
            raise ValueError("官方休市日历归档无效") from None
        self._save("gbbq.zip", payload)
        return calendar

    def fetch(self, day: date) -> DailyArchive | None:
        payload = self._download(DAILY_URL.format(day=day.strftime("%Y%m%d")))
        if payload is None:
            return None
        try:
            archive = parse_daily(payload, day)
        except zipfile.BadZipFile:
            raise ValueError("官方单日 ZIP 校验失败") from None
        self._save(f"{day:%Y%m%d}.zip", payload)
        return archive
