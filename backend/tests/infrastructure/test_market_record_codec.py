import json

from easy_quant.infrastructure.persistence.market_record_codec import decode_record, encode_record


def test_codec_is_lossless_and_leaves_revision_metadata_queryable():
    row = {
        "source": "eastmoney",
        "report_period": "2025-12-31",
        "statement_scope": "合并",
        "category": None,
        "available_at": "2026-03-21T23:59:59+08:00",
        "amount": "1234567890.123456789",
        "missing": None,
        "raw_fields": {f"财务科目{index}": str(index) for index in range(300)},
    }
    packed = encode_record(row)
    assert len(packed.encode()) < len(json.dumps(row, ensure_ascii=False).encode()) * 0.6
    assert json.loads(packed)["report_period"] == row["report_period"]
    assert decode_record(packed) == row
    assert decode_record(json.dumps(row)) == row
    assert decode_record(encode_record({"missing": None, "zero": "0"})) == {
        "missing": None,
        "zero": "0",
    }
