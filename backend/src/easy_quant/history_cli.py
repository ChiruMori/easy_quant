from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy.exc import SQLAlchemyError

from easy_quant.application.services.history_import import HistoryImportResult, import_history
from easy_quant.config import BACKEND_ROOT, get_settings
from easy_quant.infrastructure.imports.tdx import (
    ARCHIVE_URL,
    FORMAT_VERSION,
    TdxArchive,
    download_archive,
    sha256_stream,
)
from easy_quant.infrastructure.imports.tdx_bulk import LocalFileHistoryLoader
from easy_quant.infrastructure.persistence.repositories.history_import import SqlHistoryStore
from easy_quant.infrastructure.persistence.session import (
    create_database_engine,
    create_session_factory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="通达信官方全量 A 股历史日线下载与导入")
    parser.add_argument("action", choices=("download", "inspect", "import"))
    parser.add_argument("--archive", type=Path, default=BACKEND_ROOT / ".local-data/tdx/hsjday.zip")
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument(
        "--local-infile",
        action="store_true",
        help="数据库已启用 LOCAL INFILE 时使用原生批量导入；仅本次 CLI 连接启用",
    )
    args = parser.parse_args()
    if args.action == "download":
        with httpx.Client(timeout=60, follow_redirects=True, trust_env=False) as client:
            download_archive(client, args.archive)
        print(f"下载完成：{args.archive}", flush=True)
        return 0
    with args.archive.open("rb") as archive_stream:
        digest = sha256_stream(archive_stream)
    with zipfile.ZipFile(args.archive) as zip_archive:
        archive = TdxArchive(zip_archive)
        if args.action == "inspect":
            counts: dict[str, int] = {}
            rows = 0
            first = last = None
            for member, symbol in archive.members():
                bars = archive.read_bars(member, symbol)
                counts[member.replace("\\", "/").split("/")[-1][:2]] = (
                    counts.get(member.replace("\\", "/").split("/")[-1][:2], 0) + 1
                )
                rows += len(bars)
                if bars:
                    first = min(first, bars[0].trading_day) if first else bars[0].trading_day
                    last = max(last, bars[-1].trading_day) if last else bars[-1].trading_day
            print(
                json.dumps(
                    {
                        "sha256": digest,
                        "stocks": counts,
                        "rows": rows,
                        "first_day": str(first),
                        "last_day": str(last),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        engine = create_database_engine(
            get_settings().database_url.get_secret_value(), local_infile=args.local_infile
        )
        loader = (
            LocalFileHistoryLoader(args.archive.parent / "batches") if args.local_infile else None
        )
        store = SqlHistoryStore(create_session_factory(engine), lambda: datetime.now(UTC), loader)

        def progress(result: HistoryImportResult) -> None:
            done = result.imported_stocks + result.skipped_stocks + len(result.failures)
            print(
                json.dumps(
                    {
                        "completed": done,
                        "stock_files": result.stock_files,
                        "imported_stocks": result.imported_stocks,
                        "skipped_stocks": result.skipped_stocks,
                        "imported_rows": result.imported_rows,
                        "failed_stocks": len(result.failures),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

        try:
            result = import_history(
                archive, store, digest, batch_size=args.batch_size, progress=progress
            )
        except KeyboardInterrupt:
            print("导入已中断；未提交批次已回滚，重跑可跳过已完成股票", flush=True)
            return 130
        except SQLAlchemyError as error:
            print(f"数据库不可用（{type(error).__name__}）；重跑可继续已完成检查点", flush=True)
            return 1
        finally:
            engine.dispose()
    report = {
        "source_url": ARCHIVE_URL,
        "format_version": FORMAT_VERSION,
        "archive_sha256": digest,
        "archive_bytes": args.archive.stat().st_size,
        "adjustment": "none",
        "volume_unit": "share",
        "amount_unit": "CNY",
        "finished_at": datetime.now(UTC).isoformat(),
        **asdict(result),
    }
    report_path = args.archive.parent / f"import-{digest}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"导入报告：{report_path}", flush=True)
    return int(bool(result.failures))


if __name__ == "__main__":
    raise SystemExit(main())
