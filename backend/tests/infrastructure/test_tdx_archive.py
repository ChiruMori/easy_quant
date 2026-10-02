from __future__ import annotations

import io
import json
import struct
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from easy_quant.domain.shared.errors import ValidationError
from easy_quant.infrastructure.imports.tdx import TdxArchive, parse_day, sha256_stream, stock_symbol


def fixture_bytes() -> bytes:
    fixture = Path(__file__).parents[1] / "fixtures/imports/tdx-day-v1.json"
    return b"".join(
        struct.pack("<IIIIIfII", *row) for row in json.loads(fixture.read_text())["records"]
    )


def test_day_prices_units_and_close_availability() -> None:
    bars = parse_day(fixture_bytes(), "000001")
    assert len(bars) == 2
    assert bars[0].close == Decimal("10.5")
    assert bars[0].volume == 1000
    assert bars[0].amount == Decimal("12345.5")
    assert bars[0].available_at.astimezone(UTC) == datetime(2026, 9, 29, 7, tzinfo=UTC)


def test_extended_volume_keeps_share_remainder() -> None:
    data = struct.pack("<IIIIIfII", 20260929, 1000, 1100, 900, 1050, 1200, 30, 0xC3640011)
    assert parse_day(data, "000001")[0].volume == 3017


def test_float32_amount_is_rounded_to_database_precision_before_writing() -> None:
    data = struct.pack("<IIIIIfII", 20260929, 1000, 1100, 900, 1050, 0.03125, 30, 0)
    assert parse_day(data, "000001")[0].amount == Decimal("0.0313")


@pytest.mark.parametrize(
    "member,expected",
    [
        ("sh/lday/sh600000.day", "600000"),
        ("sz\\lday\\sz000001.day", "000001"),
        ("bj920001.day", "920001"),
        ("sh688001.day", "688001"),
        ("sh000001.day", None),
        ("sz399001.day", None),
        ("sh510300.day", None),
        ("sz200001.day", None),
        ("sh900901.day", None),
        ("sz123001.day", None),
        ("sh600000.01", None),
    ],
)
def test_only_a_share_daily_files_are_selected(member, expected) -> None:
    assert stock_symbol(member) == expected


@pytest.mark.parametrize(
    "data",
    [
        b"bad",
        struct.pack("<IIIIIfII", 20260230, 1000, 1100, 900, 1050, 1, 1, 0),
        fixture_bytes() * 2,
    ],
)
def test_invalid_length_date_and_duplicate_order_fail(data) -> None:
    with pytest.raises(ValueError):
        parse_day(data, "000001")


def test_nan_and_invalid_price_fail_before_persistence() -> None:
    for amount, close in [(float("nan"), 1050), (float("inf"), 1050), (-0.00001, 1050), (1, 2000)]:
        data = struct.pack("<IIIIIfII", 20260929, 1000, 1100, 900, close, amount, 1, 0)
        with pytest.raises(ValidationError):
            parse_day(data, "000001")


def test_zip_paths_and_duplicates_without_extracting_to_storage() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("sz\\lday\\sz000001.day", fixture_bytes())
        archive.writestr("sh/lday/sh000001.day", fixture_bytes())
    stream.seek(0)
    with zipfile.ZipFile(stream) as archive:
        reader = TdxArchive(archive)
        assert [(path.replace("\\", "/"), symbol) for path, symbol in reader.members()] == [
            ("sz/lday/sz000001.day", "000001")
        ]
        assert len(reader.read_bars(*reader.members()[0])) == 2
    with zipfile.ZipFile(stream, "a") as archive:
        archive.writestr("sz000001.day", fixture_bytes())
    stream.seek(0)
    with zipfile.ZipFile(stream) as archive, pytest.raises(ValueError, match="重复"):
        TdxArchive(archive).members()


def test_archive_identity_is_stable() -> None:
    assert (
        sha256_stream(io.BytesIO(b"abc"))
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
