import py_mini_racer
import pytest

from easy_quant.infrastructure.data_sources.akshare.daily import decode_sina_index


@pytest.mark.parametrize("modern", [False, True], ids=["linux-legacy", "modern"])
@pytest.mark.parametrize("failure", [None, "eval", "call"])
def test_decoder_supports_both_lifecycles_and_preserves_timeouts(monkeypatch, modern, failure):
    events: list[tuple[str, int | None]] = []
    rows = [{"date": "2026-10-15", "close": "100"}]

    class LegacyRuntime:
        # 与 Linux 依赖相同：无 __enter__、__exit__ 或 close。
        def eval(self, script, *, timeout):
            assert "function d" in script
            events.append(("eval", timeout))
            if failure == "eval":
                raise ValueError("eval failed")

        def call(self, function, encoded, *, timeout):
            assert (function, encoded) == ("d", "fixture-v1")
            events.append(("call", timeout))
            if failure == "call":
                raise ValueError("call failed")
            return rows

    class ModernRuntime(LegacyRuntime):
        def close(self):
            events.append(("close", None))

    monkeypatch.setattr(py_mini_racer, "MiniRacer", ModernRuntime if modern else LegacyRuntime)
    if failure:
        with pytest.raises(ValueError, match=f"{failure} failed"):
            decode_sina_index("fixture-v1")
    else:
        assert decode_sina_index("fixture-v1") == rows
    expected: list[tuple[str, int | None]] = [("eval", 5000)]
    if failure != "eval":
        expected.append(("call", 5000))
    if modern:
        expected.append(("close", None))
    assert events == expected
