from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from itertools import islice

from easy_quant.application.ports.market_data import NormalizedRecordRepository

logger = logging.getLogger(__name__)


class NormalizationService:
    def __init__(self, repository: NormalizedRecordRepository) -> None:
        self.repository = repository

    def replace(
        self, dataset_key: str, rows: Iterable[Mapping[str, object]], *, batch_size: int = 1000
    ) -> int:
        logger.warning("重复业务键将由新数据直接覆盖", extra={"dataset": dataset_key})
        iterator = iter(rows)
        total = 0
        while batch := tuple(islice(iterator, batch_size)):
            total += self.repository.upsert_many(dataset_key, batch)
        return total
