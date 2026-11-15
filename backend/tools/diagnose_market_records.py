"""只读、有界基本面诊断，不输出原始载荷或连接身份。"""

from diagnose_database import QUERIES, main

QUERIES.clear()
QUERIES.update(
    sizes="""SELECT table_name,table_rows,data_length,index_length,data_free
        FROM information_schema.tables WHERE table_schema=DATABASE()
        AND table_name IN ('market_records','daily_bars','raw_cache')""",
    row_format="""SELECT row_format,create_options FROM information_schema.tables
        WHERE table_schema=DATABASE() AND table_name='market_records'""",
    indexes="""SELECT index_name,seq_in_index,column_name,cardinality
        FROM information_schema.statistics WHERE table_schema=DATABASE()
        AND table_name='market_records'""",
    datasets="""SELECT dataset_key,COUNT(*) AS n FROM market_records
        FORCE INDEX(ix_market_records_symbol_dataset_at) GROUP BY dataset_key""",
    sample="""SELECT dataset_key,COUNT(*) AS n,AVG(OCTET_LENGTH(payload_json)) AS avg_bytes,
        MAX(OCTET_LENGTH(payload_json)) AS max_bytes,
        AVG(OCTET_LENGTH(JSON_EXTRACT(payload_json,'$.raw_fields'))) AS raw_bytes,
        AVG(OCTET_LENGTH(JSON_EXTRACT(payload_json,'$.field_labels'))) AS label_bytes
        FROM (SELECT dataset_key,payload_json FROM market_records
        WHERE symbol IN ('000001','000002','600519','300001','605339') LIMIT 2000) s
        GROUP BY dataset_key""",
    page_plan="""EXPLAIN SELECT payload_json FROM market_records
        WHERE symbol='000001' AND dataset_key='financial-indicators'
        AND available_at<='2026-11-14' ORDER BY available_at DESC,record_key DESC LIMIT 10""",
    checkpoint_counts="""SELECT namespace,COUNT(*) AS n FROM runtime_documents
        WHERE namespace='collection_checkpoints' GROUP BY namespace""",
)

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(type(error).__name__)
        raise SystemExit(1) from None
