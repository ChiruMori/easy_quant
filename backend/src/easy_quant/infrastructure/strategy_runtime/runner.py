from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

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
