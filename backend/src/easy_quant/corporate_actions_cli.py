"""默认只读的公司行为检查、候选迁移及公开证据导入。"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from easy_quant.application.services.corporate_actions import dividend_candidates, import_manifest
from easy_quant.config import get_settings
from easy_quant.domain.market_data.corporate_actions import DATASET
from easy_quant.domain.market_data.research_actions import TDX_PRICE_DATASET
from easy_quant.infrastructure.imports.tdx_corporate_actions import archive_candidates
from easy_quant.infrastructure.persistence.repositories.runtime import SqlAlchemyMarketDataStore
from easy_quant.infrastructure.persistence.session import (
    create_database_engine,
    create_session_factory,
)


def inspect_symbol(store, symbol: str) -> dict:
    records = store.list_records(DATASET, symbol)
    adjustment = store.bar_adjustment(symbol)
    return {
        "symbol": symbol,
        "stored_adjustment": adjustment,
        "raw_compatible": adjustment in {None, "none"},
        "events": [row for row in records if row.get("record_kind") == "event"],
        "coverage": [row for row in records if row.get("record_kind") == "coverage"],
        "candidates": [row for row in records if row.get("record_kind") == "candidate"],
        "price_publications": store.list_records(TDX_PRICE_DATASET, symbol),
        "equity_checks": store.list_records("tdx-equity-checks", symbol),
        "required_action": "旧复权行情不可逆，保留并重新采集原价；未自动修改"
        if adjustment not in {None, "none"}
        else "查看价格发布中的 issues 与权益检查中的 missing；原价无需重写",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=["audit", "migrate-dividends", "import-gbbq", "import", "prepare-tdx"]
    )
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", action="store_true", help="明确写入候选/事件；永不重写行情")
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="重新读取原价上下文，修复历史行情变更后的价格调整",
    )
    args = parser.parse_args()
    if args.mode in {"audit", "migrate-dividends"} and not args.symbol:
        parser.error("必须至少指定一个 --symbol，避免无界扫描")
    if args.mode in {"import", "import-gbbq", "prepare-tdx"} and args.input is None:
        parser.error("必须指定 --input")
    engine = create_database_engine(get_settings().database_url.get_secret_value())
    try:
        with create_session_factory(engine)() as session:
            store = SqlAlchemyMarketDataStore(session)
            now = datetime.now(UTC)
            if args.mode == "audit":
                report = [inspect_symbol(store, symbol) for symbol in args.symbol]
            elif args.mode == "prepare-tdx":
                from easy_quant.application.services.tdx_price_sync import prepare_tdx_prices

                completed = 0

                def progress(row):
                    nonlocal completed
                    completed += 1
                    if completed % 100 == 0:
                        print(f"价格整理已处理 {completed} 只，当前 {row['symbol']}", flush=True)

                report = prepare_tdx_prices(
                    store,
                    args.input.read_bytes(),
                    now,
                    symbols=set(args.symbol) or None,
                    apply=args.apply,
                    force_rebuild=args.force_rebuild,
                    progress=progress,
                )
                if args.apply:
                    from types import SimpleNamespace

                    from easy_quant.infrastructure.persistence.repositories.jobs import (
                        SqlAlchemyJobRepository,
                    )
                    from easy_quant.worker.handlers.corporate_actions import (
                        enqueue_equity_enrichment,
                    )

                    job = enqueue_equity_enrichment(
                        SimpleNamespace(market_data=store, jobs=SqlAlchemyJobRepository(session)),
                        now,
                    )
                    report["equity_job_id"] = job.id
            elif args.mode == "import":
                report = import_manifest(
                    store, json.loads(args.input.read_text(encoding="utf-8")), now, apply=args.apply
                )
            else:
                candidates = (
                    archive_candidates(args.input.read_bytes(), now, set(args.symbol) or None)
                    if args.mode == "import-gbbq"
                    else dividend_candidates(
                        [
                            row
                            for symbol in args.symbol
                            for row in store.list_records("dividend-plans", symbol)
                        ]
                    )
                )
                if args.apply:
                    store.upsert_records(DATASET, candidates)
                report = {
                    "applied": args.apply,
                    "candidate_count": len(candidates),
                    "trusted_events_added": 0,
                    "candidates": candidates,
                }
            output = json.dumps(report, ensure_ascii=False, indent=2, default=str)
            if args.output:
                args.output.write_text(output, encoding="utf-8")
            else:
                print(output)
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
