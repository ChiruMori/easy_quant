from __future__ import annotations

import argparse
import json
import signal
from dataclasses import asdict
from datetime import UTC, date, datetime

import httpx

from easy_quant.application.services.corporate_actions import sync_tdx_candidates
from easy_quant.application.services.tdx_incremental import TdxDailyUpdateService
from easy_quant.config import BACKEND_ROOT, get_settings
from easy_quant.infrastructure.imports.tdx_daily import OfficialDailyFeed
from easy_quant.infrastructure.persistence.repositories.runtime import SqlAlchemyMarketDataStore
from easy_quant.infrastructure.persistence.repositories.tdx_daily import SqlDailyStore
from easy_quant.infrastructure.persistence.session import (
    create_database_engine,
    create_session_factory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="通达信官方 A 股盘后增量更新与缺日恢复")
    parser.add_argument("--start-day", type=date.fromisoformat)
    parser.add_argument("--end-day", type=date.fromisoformat)
    parser.add_argument(
        "--replay", action="store_true", help="显式按日恢复官方数据，必须提供起止日期"
    )
    args = parser.parse_args()
    if args.replay and (args.start_day is None or args.end_day is None):
        parser.error("--replay必须同时提供--start-day和--end-day")
    engine = create_database_engine(get_settings().database_url.get_secret_value())
    directory = BACKEND_ROOT / ".local-data/tdx/daily"
    stop_requested = False

    def request_stop(_signum, _frame) -> None:
        nonlocal stop_requested
        stop_requested = True

    def progress(result) -> None:
        print(json.dumps(asdict(result), ensure_ascii=False), flush=True)
        if stop_requested:
            raise KeyboardInterrupt

    def corporate_archive(payload: bytes) -> None:
        with create_session_factory(engine)() as session:
            sync_tdx_candidates(SqlAlchemyMarketDataStore(session), payload, datetime.now(UTC))

    previous_handler = signal.signal(signal.SIGINT, request_stop)
    try:
        with httpx.Client(timeout=60, follow_redirects=True, trust_env=False) as client:
            service = TdxDailyUpdateService(
                OfficialDailyFeed(client, directory, corporate_archive=corporate_archive),
                SqlDailyStore(create_session_factory(engine), lambda: datetime.now(UTC)),
                lambda: datetime.now(UTC),
            )
            result = service.update(
                start_day=args.start_day,
                end_day=args.end_day,
                replay=args.replay,
                progress=progress,
            )
        report = {
            "format_version": "tdx-md1-v1",
            "finished_at": datetime.now(UTC).isoformat(),
            **asdict(result),
        }
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "latest-update.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return int(bool(result.unresolved))
    except (ValueError, RuntimeError) as error:
        print(str(error), flush=True)
        return 1
    except KeyboardInterrupt:
        print("增量已中断；未提交日期会回滚，重新运行可恢复", flush=True)
        return 130
    finally:
        signal.signal(signal.SIGINT, previous_handler)
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
