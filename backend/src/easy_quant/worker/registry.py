from __future__ import annotations

from easy_quant.application.ports.jobs import JobHandler
from easy_quant.domain.shared.errors import ValidationError


class JobHandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        if job_type in self._handlers:
            raise ValidationError("任务处理器重复注册", {"job_type": job_type})
        self._handlers[job_type] = handler

    def get(self, job_type: str) -> JobHandler:
        try:
            return self._handlers[job_type]
        except KeyError as exc:
            raise ValidationError("未知任务类型", {"job_type": job_type}) from exc
