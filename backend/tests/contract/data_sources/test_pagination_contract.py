from easy_quant.infrastructure.data_sources.eastmoney.adapters import diagnose_page


def test_page_count_mismatch_is_visible() -> None:
    diagnosis = diagnose_page(total=5, rows=[1], page=2, page_size=2)
    assert diagnosis == {"page": 2, "expected": 2, "actual": 1, "complete": False}


def test_last_partial_page_is_complete() -> None:
    assert diagnose_page(5, [1], 3, 2)["complete"] is True
