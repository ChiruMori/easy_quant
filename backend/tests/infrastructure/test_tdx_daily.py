from __future__ import annotations

import io
import json
import struct
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from easy_quant.domain.shared.errors import DomainError
from easy_quant.infrastructure.imports.tdx_daily import (
    OfficialDailyFeed,
    parse_calendar,
    parse_daily,
)

DAY = date(2026, 9, 30)


def daily_members() -> dict[str, bytes]:
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/imports/tdx-md1-v1.json").read_text()
    )
    members = {}
    for market, row in fixture["markets"].items():
        cod, md1 = bytearray(150), bytearray(512)
        cod[:6] = row["symbol"].encode("ascii")
        struct.pack_into("<H", cod, 32, 0)
        struct.pack_into("<dddd", md1, 12, *row["prices"])
        struct.pack_into("<Q", md1, 56, row["volume"])
        struct.pack_into("<d", md1, 72, row["amount"])
        members[f"{market}260930.cod"] = bytes(cod)
        members[f"{market}260930.md1"] = bytes(md1)
    return members


def zip_bytes(members: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return output.getvalue()


def calendar_bytes(content: bytes = b"Y36=2026,0925,1001,1002,\n") -> bytes:
    return zip_bytes({"zhb.zip": zip_bytes({"needini.dat": content})})


def test_daily_normalizes_day_compatible_precision_volume_and_suspension() -> None:
    result = parse_daily(zip_bytes(daily_members()), DAY)
    assert len(result.bars) == 2 and result.suspended == 1
    bar = result.bars[0]
    assert bar.symbol == "600000" and bar.close == Decimal("10.5")
    assert bar.volume == Decimal("4500000017")
    expected = struct.unpack("<f", struct.pack("<f", 123456789.125))[0]
    assert bar.amount == Decimal(str(expected)).quantize(Decimal("0.0001"))
    assert bar.available_at.isoformat() == "2026-09-30T15:00:00+08:00"


@pytest.mark.parametrize(
    "fault",
    [
        "missing-market",
        "wrong-date",
        "short-cod",
        "short-md1",
        "out-of-range",
        "duplicate",
        "nan",
        "negative",
        "invalid-ohlc",
        "negative-suspended",
        "oversize-volume",
    ],
)
def test_daily_corruption_rejects_entire_archive(fault) -> None:
    members = daily_members()
    if fault == "missing-market":
        del members["bj260930.md1"]
    elif fault == "wrong-date":
        members["sh260929.md1"] = members.pop("sh260930.md1")
    elif fault == "short-cod":
        members["sh260930.cod"] = b"short"
    elif fault == "short-md1":
        members["sh260930.md1"] = b"short"
    elif fault == "out-of-range":
        cod = bytearray(members["sh260930.cod"])
        struct.pack_into("<H", cod, 32, 5)
        members["sh260930.cod"] = bytes(cod)
    elif fault == "duplicate":
        members["sh260930.cod"] *= 2
    else:
        key = "bj260930.md1" if fault == "negative-suspended" else "sh260930.md1"
        md1 = bytearray(members[key])
        if fault == "oversize-volume":
            struct.pack_into("<Q", md1, 56, 0xFFFFFFFFFFFFFFFF)
        else:
            struct.pack_into(
                "<d",
                md1,
                12,
                float("nan")
                if fault == "nan"
                else -1
                if fault in {"negative", "negative-suspended"}
                else 100,
            )
        members[key] = bytes(md1)
    with pytest.raises((ValueError, DomainError)):
        parse_daily(zip_bytes(members), DAY)


def test_calendar_recognizes_only_declared_years() -> None:
    calendar = parse_calendar(calendar_bytes())
    assert calendar.years == frozenset({2026})
    assert calendar.closed(date(2026, 10, 1))
    assert calendar.closed(date(2026, 10, 3))
    assert not calendar.closed(date(2027, 10, 1))


@pytest.mark.parametrize(
    "content", [b"invalid", b"Y1=2026,0230,", b"Y1=2026,invalid,", b"Y1=2026,1001,\nY2=2026,1002,"]
)
def test_invalid_calendar_fails(content) -> None:
    with pytest.raises(ValueError):
        parse_calendar(calendar_bytes(content))


@pytest.mark.parametrize("status", [404, 503, 200])
def test_feed_uses_offline_transport_and_sanitizes_errors(monkeypatch, status) -> None:
    saved = []
    monkeypatch.setattr(
        OfficialDailyFeed, "_save", lambda _self, name, _payload: saved.append(name)
    )
    payload = zip_bytes(daily_members())
    transport = httpx.MockTransport(lambda _request: httpx.Response(status, content=payload))
    with httpx.Client(transport=transport, trust_env=False) as client:
        feed = OfficialDailyFeed(client, Path("unused"))
        if status == 503:
            with pytest.raises(RuntimeError) as error:
                feed.fetch(DAY)
            assert "https://" not in str(error.value)
        elif status == 404:
            assert feed.fetch(DAY) is None and not saved
        else:
            assert feed.fetch(DAY) is not None and saved == ["20260930.zip"]


@pytest.mark.parametrize("fault", ["short", "oversize", "corrupt"])
def test_feed_rejects_incomplete_or_invalid_download_before_saving(monkeypatch, fault) -> None:
    saved = []
    monkeypatch.setattr(OfficialDailyFeed, "_save", lambda *_args: saved.append(True))
    payload = (
        b"corrupt"
        if fault == "corrupt"
        else b"x" * (16 * 1024 * 1024 + 1)
        if fault == "oversize"
        else zip_bytes(daily_members())
    )
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            content=payload,
            headers={"content-length": str(len(payload) + int(fault == "short"))},
        )
    )
    with httpx.Client(transport=transport, trust_env=False) as client, pytest.raises(ValueError):
        OfficialDailyFeed(client, Path("unused")).fetch(DAY)
    assert not saved


def test_calendar_404_fails_without_falling_back_to_guessed_holidays(monkeypatch) -> None:
    monkeypatch.setattr(OfficialDailyFeed, "_save", lambda *_args: pytest.fail("失败日历不保存"))
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(404)), trust_env=False
        ) as client,
        pytest.raises(RuntimeError, match="休市日历"),
    ):
        OfficialDailyFeed(client, Path("unused")).calendar()
