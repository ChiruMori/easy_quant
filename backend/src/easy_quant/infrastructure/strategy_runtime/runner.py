from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import date
from pathlib import Path
from typing import Any

from easy_quant.domain.strategies.entities import (
    Signal,
    StrategyRun,
    StrategyRunStatus,
    StrategyVersion,
)


class SubprocessStrategyRunner:
    def __init__(
        self,
        timeout_seconds: float = 5,
        output_limit: int = 65536,
        result_limit: int = 8 * 1024 * 1024,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.output_limit = output_limit
        self.result_limit = result_limit

    def run(
        self,
        version: StrategyVersion,
        parameters: dict[str, object],
        context_data: dict[str, object] | None = None,
        *,
        phase: str = "before_market",
    ) -> StrategyRun:
        return self.run_many(version, parameters, [(context_data or {}, phase)])[0]

    def run_many(
        self,
        version: StrategyVersion,
        parameters: dict[str, object],
        calls: list[tuple[dict[str, object], str]],
    ) -> list[StrategyRun]:
        runs = [
            StrategyRun(
                f"run-{version.id}-{index}", version.id, StrategyRunStatus.RUNNING, parameters
            )
            for index in range(len(calls))
        ]
        child = Path(__file__).with_name("child.py")
        environment = {
            key: value
            for key, value in os.environ.items()
            if not any(token in key.upper() for token in ("SECRET", "TOKEN", "PASSWORD", "KEY"))
        }
        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(child)],
                input=json.dumps(
                    {
                        "source_code": version.source_code,
                        "parameters": parameters,
                        "calls": [
                            {"context": context_data, "phase": phase}
                            for context_data, phase in calls
                        ],
                    }
                ),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                env=environment,
                check=False,
            )
        except subprocess.TimeoutExpired:
            for run in runs:
                run.status, run.error = StrategyRunStatus.TIMED_OUT, "策略运行超时"
            return runs
        if len(completed.stdout.encode("utf-8")) > self.result_limit:
            for run in runs:
                run.status, run.error = StrategyRunStatus.FAILED, "策略结果超过传输限制"
            return runs
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            for run in runs:
                run.status, run.error = StrategyRunStatus.FAILED, "策略子进程返回无效结果"
            return runs
        results = payload.get("results", [])
        if not payload.get("ok") or not isinstance(results, list) or len(results) != len(runs):
            for run in runs:
                run.status = StrategyRunStatus.FAILED
                run.error = str(payload.get("error") or "策略子进程返回无效结果")
            return runs
        for run, result in zip(runs, results, strict=True):
            self._apply_result(run, result)
        return runs

    def _apply_result(self, run: StrategyRun, payload: object) -> None:
        if not isinstance(payload, dict):
            run.status, run.error = StrategyRunStatus.FAILED, "策略子进程返回无效结果"
            return
        raw_stdout = str(payload.get("stdout", ""))
        if len(raw_stdout.encode("utf-8")) > self.output_limit:
            run.status, run.error = StrategyRunStatus.FAILED, "策略输出超过限制"
            run.stdout = raw_stdout.encode("utf-8")[: self.output_limit].decode(
                "utf-8", errors="ignore"
            )
            return
        run.stdout = raw_stdout
        run.error = str(payload["error"]) if payload.get("error") else None
        if not payload.get("ok"):
            run.status = StrategyRunStatus.FAILED
            return
        try:
            run.signals = [
                Signal(
                    str(item["symbol"]),
                    str(item["action"]),
                    __import__("decimal").Decimal(str(item["quantity"])),
                    str(item.get("reason", "")),
                    __import__("decimal").Decimal(str(item["trigger_price"]))
                    if item.get("trigger_price") is not None
                    else None,
                )
                for item in payload["signals"]
            ]
        except (KeyError, TypeError, ValueError):
            run.status, run.error = StrategyRunStatus.FAILED, "策略信号格式无效"
            return
        run.status = StrategyRunStatus.SUCCEEDED


class StreamingStrategyRunner:
    """单个回测任务复用受限子进程，逐日发送新增行情而非全量历史。"""

    def __init__(
        self,
        version: StrategyVersion,
        parameters: dict[str, object],
        *,
        timeout_seconds: float = 30,
        output_limit: int = 65536,
        result_limit: int = 8 * 1024 * 1024,
    ) -> None:
        self.version = version
        self.parameters = parameters
        self.timeout_seconds = timeout_seconds
        self.result_limit = result_limit
        self._decoder = SubprocessStrategyRunner(timeout_seconds, output_limit, result_limit)
        child = Path(__file__).with_name("child.py")
        environment = {
            key: value
            for key, value in os.environ.items()
            if not any(token in key.upper() for token in ("SECRET", "TOKEN", "PASSWORD", "KEY"))
        }
        self._process = subprocess.Popen(
            [sys.executable, "-I", str(child), "--stream"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=environment,
        )
        self._reader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="strategy-stream")
        try:
            ready = self._exchange({"source_code": version.source_code, "parameters": parameters})
            if not ready.get("ok") or not ready.get("ready"):
                raise RuntimeError(str(ready.get("error") or "策略子进程初始化失败"))
        except Exception:
            self.close()
            raise

    def __enter__(self) -> StreamingStrategyRunner:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        process = self._process
        if process.poll() is None:
            try:
                assert process.stdin is not None
                process.stdin.write('{"stop":true}\n')
                process.stdin.flush()
                process.wait(timeout=1)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait()
        if process.stdin is not None:
            process.stdin.close()
        if process.stdout is not None:
            process.stdout.close()
        self._reader.shutdown(wait=False, cancel_futures=True)

    def _exchange(self, request: dict[str, object]) -> dict[str, Any]:
        assert self._process.stdin is not None and self._process.stdout is not None
        # Windows 子进程默认控制台编码未必是 UTF-8；行协议保持纯 ASCII。
        self._process.stdin.write(json.dumps(request, ensure_ascii=True, default=str) + "\n")
        self._process.stdin.flush()
        future = self._reader.submit(self._process.stdout.readline)
        try:
            line = future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError:
            self._process.kill()
            self._process.wait()
            raise
        if not line:
            raise RuntimeError("策略子进程已退出")
        if len(line.encode("utf-8")) > self.result_limit:
            raise RuntimeError("策略结果超过传输限制")
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise RuntimeError("策略子进程返回无效结果")
        return payload

    def run_day(
        self,
        trading_day: date,
        *,
        expire_before: date,
        prior_before: list[dict[str, object]],
        prior_after: list[dict[str, object]],
        today_after: list[dict[str, object]],
        today_symbols: list[str],
        current_prices: dict[str, float],
        records: dict[str, object] | None = None,
    ) -> list[StrategyRun]:
        request = _day_request(
            trading_day,
            expire_before,
            prior_before,
            prior_after,
            today_after,
            today_symbols,
            current_prices,
            records,
        )
        return self._run_request(
            trading_day, ("before_market", "on_market", "after_market"), request
        )

    def run_phase(
        self,
        trading_day: date,
        *,
        phase: str,
        expire_before: date,
        prior_before: list[dict[str, object]],
        prior_after: list[dict[str, object]],
        today_after: list[dict[str, object]],
        today_symbols: list[str],
        current_prices: dict[str, float],
        positions: dict[str, str],
        cash: str,
        records: dict[str, object] | None = None,
    ) -> StrategyRun:
        request = _day_request(
            trading_day,
            expire_before,
            prior_before,
            prior_after,
            today_after,
            today_symbols,
            current_prices,
            records,
        )
        request.update({"phase": phase, "positions": dict(positions), "cash": cash})
        return self._run_request(trading_day, (phase,), request)[0]

    def _run_request(
        self, trading_day: date, phases: tuple[str, ...], request: dict[str, object]
    ) -> list[StrategyRun]:
        runs = [
            StrategyRun(
                f"run-{self.version.id}-{trading_day.isoformat()}-{phase}",
                self.version.id,
                StrategyRunStatus.RUNNING,
                self.parameters,
            )
            for phase in phases
        ]
        try:
            payload = self._exchange(request)
        except FutureTimeoutError:
            for run in runs:
                run.status, run.error = StrategyRunStatus.TIMED_OUT, "策略运行超时"
            return runs
        except (OSError, RuntimeError, json.JSONDecodeError) as error:
            for run in runs:
                run.status, run.error = StrategyRunStatus.FAILED, str(error)
            return runs
        results = payload.get("results", [])
        if not payload.get("ok") or not isinstance(results, list) or len(results) != len(runs):
            for run in runs:
                run.status = StrategyRunStatus.FAILED
                run.error = str(payload.get("error") or "策略子进程返回无效结果")
            return runs
        for run, result in zip(runs, results, strict=True):
            self._decoder._apply_result(run, result)
        return runs


def _day_request(
    trading_day: date,
    expire_before: date,
    prior_before: list[dict[str, object]],
    prior_after: list[dict[str, object]],
    today_after: list[dict[str, object]],
    today_symbols: list[str],
    current_prices: dict[str, float],
    records: dict[str, object] | None,
) -> dict[str, object]:
    def price_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {"symbol": row["symbol"], "trading_day": row["trading_day"], "close": row["close"]}
            for row in rows
        ]

    return {
        "trading_day": trading_day.isoformat(),
        "expire_before": expire_before.isoformat(),
        "prior_before": price_rows(prior_before),
        "prior_after": price_rows(prior_after),
        "today_after": price_rows(today_after),
        "today_symbols": today_symbols,
        "current_prices": current_prices,
        "records": records or {},
    }
