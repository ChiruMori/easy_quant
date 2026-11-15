"""基本面 JSON 无损压缩；用于 SQL 去重的元数据仍保留为顶层字段。"""

import base64
import json
import zlib

METADATA = ("source", "report_period", "statement_scope", "category", "item_name", "record_date")


def encode_record(row: dict) -> str:
    plain = json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(plain.encode()) < 1000:
        return plain
    metadata = {key: row[key] for key in METADATA if key in row}
    rest = {key: value for key, value in row.items() if key not in METADATA}
    metadata["_compressed_v1"] = base64.b64encode(
        zlib.compress(
            json.dumps(rest, ensure_ascii=False, separators=(",", ":"), default=str).encode()
        )
    ).decode("ascii")
    packed = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    return packed if len(packed.encode()) < len(plain.encode()) else plain


def decode_record(payload: str) -> dict:
    row = json.loads(payload)
    # 旧的业务字典若恰有同名字段，仍按普通记录返回。
    if "_compressed_v1" in row and set(row) <= {*METADATA, "_compressed_v1"}:
        compressed = row.pop("_compressed_v1")
        row.update(json.loads(zlib.decompress(base64.b64decode(compressed, validate=True))))
    return row
