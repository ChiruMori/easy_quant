"""只读有限样本，比较新编码；不输出原始记录，不写库。"""

import json

import pymysql
from sqlalchemy.engine import make_url

from easy_quant.config import get_settings
from easy_quant.domain.market_data.fundamentals import FINANCIAL_DATASETS
from easy_quant.infrastructure.persistence.market_record_codec import decode_record, encode_record


def main():
    url = make_url(get_settings().database_url.get_secret_value())
    connection = pymysql.connect(
        host=url.host or "localhost",
        port=url.port or 3306,
        user=url.username,
        password=url.password,
        database=url.database,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
        read_timeout=8,
        write_timeout=8,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("SET SESSION max_statement_time=5")
            for dataset in FINANCIAL_DATASETS:
                cursor.execute(
                    "SELECT payload_json FROM market_records WHERE dataset_key=%s LIMIT 200",
                    (dataset,),
                )
                rows = cursor.fetchall()
                before = after = 0
                for (payload,) in rows:
                    record = decode_record(payload)
                    encoded = encode_record(record)
                    assert decode_record(encoded) == record
                    before += len(payload.encode())
                    after += len(encoded.encode())
                print(
                    json.dumps(
                        {
                            "dataset": dataset,
                            "sample": len(rows),
                            "before_bytes": before,
                            "after_bytes": after,
                        }
                    ),
                    flush=True,
                )
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(type(error).__name__)
        raise SystemExit(1) from None
