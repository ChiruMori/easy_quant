import json
import logging

from easy_quant.infrastructure.logging import redact, structured_log


def test_nested_sensitive_fields_are_redacted(caplog) -> None:
    assert redact({"password": "bad", "nested": {"api_key": "secret", "safe": 1}}) == {
        "password": "***",
        "nested": {"api_key": "***", "safe": 1},
    }
    with caplog.at_level(logging.INFO):
        structured_log(logging.getLogger("test"), "job", correlation_id="c-1", token="hidden")
    record = json.loads(caplog.records[-1].message)
    assert record == {"event": "job", "correlation_id": "c-1", "token": "***"}
