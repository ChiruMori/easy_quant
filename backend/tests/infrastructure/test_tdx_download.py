from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import cast

import httpx
import pytest

from easy_quant.infrastructure.imports import tdx
from tests.infrastructure.test_tdx_archive import fixture_bytes


class MemoryPath:
    def __init__(self, content: dict[str, bytes], name: str) -> None:
        self.content, self.name = content, name
        self.parent = self

    def mkdir(self, **_kwargs):
        pass

    def with_suffix(self, suffix):
        return MemoryPath(self.content, "archive" + suffix)

    def open(self, _mode):
        content, name = self.content, self.name

        class Output(io.BytesIO):
            def close(self):
                content[name] = self.getvalue()
                super().close()

        return Output()

    def replace(self, destination):
        self.content[destination.name] = self.content.pop(self.name)


def archive_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("sz000001.day", fixture_bytes())
    return output.getvalue()


@pytest.mark.parametrize("fault", [None, "short", "invalid-zip", "http-error"])
def test_downloader_replaces_target_only_after_complete_valid_archive(monkeypatch, fault) -> None:
    content = {"archive.zip": b"existing"}
    payload = b"invalid" if fault == "invalid-zip" else archive_bytes()
    real_zip = zipfile.ZipFile
    monkeypatch.setattr(
        tdx.zipfile,
        "ZipFile",
        lambda path: real_zip(io.BytesIO(content[path.name])),
    )
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            503 if fault == "http-error" else 200,
            content=payload,
            headers={"content-length": str(len(payload) + (1 if fault == "short" else 0))},
        )
    )
    target = cast(Path, MemoryPath(content, "archive.zip"))
    with httpx.Client(transport=transport, trust_env=False) as client:
        if fault:
            with pytest.raises((ValueError, zipfile.BadZipFile, httpx.HTTPStatusError)):
                tdx.download_archive(client, target)
            assert content["archive.zip"] == b"existing"
        else:
            tdx.download_archive(client, target)
            assert content["archive.zip"] == payload
            assert "archive.zip.part" not in content
