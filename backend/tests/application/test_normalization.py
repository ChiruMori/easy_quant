from easy_quant.application.services.normalization import NormalizationService


class RecordingRepository:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def upsert_many(self, dataset_key, rows):
        batch = list(rows)
        self.batch_sizes.append(len(batch))
        return len(batch)


def test_normalization_writes_in_bounded_batches() -> None:
    repository = RecordingRepository()
    count = NormalizationService(repository).replace(
        "daily-bars", ({"record_key": str(index)} for index in range(5)), batch_size=2
    )
    assert count == 5
    assert repository.batch_sizes == [2, 2, 1]
