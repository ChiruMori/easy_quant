"""GBBQ 公开格式解码改编自 jing2uo/tdx2db (MIT)，见 THIRD_PARTY_NOTICES.md。

只产生待核对候选；日期是供应商事件日，不伪造公告/到账/上市日期。
"""

import hashlib
import io
import math
import struct
import zipfile
from datetime import datetime
from importlib.resources import files

from easy_quant.application.services.corporate_actions import identity
from easy_quant.domain.market_data.corporate_actions import POLICY, day
from easy_quant.infrastructure.imports.tdx import stock_symbol


def decode_records(content: bytes):
    if len(content) < 4:
        raise ValueError("GBBQ 缺少记录头")
    count = struct.unpack_from("<I", content)[0]
    if not 0 < count <= 1_000_000 or len(content) != 4 + count * 29:
        raise ValueError("GBBQ 记录数量/长度不匹配")
    constants = bytes.fromhex(
        files(__package__).joinpath("gbbq_keys.hex").read_text(encoding="ascii")
    )
    keys = struct.unpack("<1044I", constants)

    def decrypt(block):
        left, right = struct.unpack("<II", block)
        left ^= keys[17]
        for index in range(16, 0, -1):
            value = (keys[0x112 + ((left >> 16) & 255)] + keys[0x12 + (left >> 24)]) & 0xFFFFFFFF
            value ^= keys[0x212 + ((left >> 8) & 255)]
            value = (value + keys[0x312 + (left & 255)]) & 0xFFFFFFFF
            left, right = (right ^ value ^ keys[index]) & 0xFFFFFFFF, left
        return struct.pack("<II", right ^ keys[0], left)

    for offset in range(4, len(content), 29):
        block = content[offset : offset + 29]
        clear = b"".join(decrypt(block[start : start + 8]) for start in (0, 8, 16)) + block[24:]
        market, code, stamp, category, *values = struct.unpack("<B7sIBffff", clear)
        try:
            symbol = code.rstrip(b"\x00").decode("ascii")
            market_name = {0: "sz", 1: "sh", 2: "bj"}.get(market)
            if market_name is None or stock_symbol(f"{market_name}{symbol}.day") is None:
                continue
            ex_date = day(f"{stamp // 10000:04d}-{stamp // 100 % 100:02d}-{stamp % 100:02d}")
            if not 1 <= category <= 255 or (
                category == 1 and not all(math.isfinite(value) for value in values)
            ):
                raise ValueError("GBBQ 类别或数值无效")
        except (UnicodeError, ValueError) as error:
            raise ValueError("GBBQ 记录无法可靠解析") from error
        yield symbol, str(ex_date), category, values


def archive_candidates(
    payload: bytes, observed_at: datetime, symbols: set[str] | None = None
) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if names.count("gbbq") != 1 or archive.getinfo("gbbq").file_size > 32 * 1024 * 1024:
            raise ValueError("GBBQ 归档成员缺失、重复或过大")
        content = archive.read("gbbq")
    digest = hashlib.sha256(content).hexdigest()
    rows = []
    for symbol, ex_date, category, values in decode_records(content):
        if symbols is not None and symbol not in symbols:
            continue
        # 流通股/增发/回购等不直接映射为除权，只保留审计候选。
        row = {
            "schema_version": POLICY,
            "record_kind": "candidate",
            "symbol": symbol,
            "source": "tdx-official-gbbq",
            "ex_date": ex_date,
            "category": category,
            "values": [format(value, ".9g") for value in values],
            "archive_identity": digest,
            "available_at": observed_at.isoformat(),
            "availability_basis": "observed",
            "price_event_candidate": category not in {2, 3, 5, 6, 7, 8, 9, 10},
            "missing": [
                "announcement_version",
                "record_date",
                "cash_pay_date",
                "shares_listing_date",
            ],
        }
        # 日期不进入内容身份：每日相同事件不重复膨胀，修订仍追加。
        row["record_key"] = identity(
            {
                key: value
                for key, value in row.items()
                if key not in {"archive_identity", "available_at"}
            }
        )
        rows.append(row)
    return rows
