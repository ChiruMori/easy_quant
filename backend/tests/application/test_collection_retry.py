from datetime import timedelta
from email.utils import format_datetime

import httpx
import pytest

from easy_quant.application.services.acquisition import AcquisitionFailed
from easy_quant.worker.handlers.collection import retry_delay


@pytest.mark.parametrize("attempt,seconds", [(1, 15), (2, 30)])
def test_transport_failure_is_not_misclassified_as_rate_limit(fixed_now, attempt, seconds):
    assert retry_delay(httpx.RemoteProtocolError("disconnected"), attempt, fixed_now) == (
        seconds,
        False,
    )


@pytest.mark.parametrize("attempt,seconds", [(1, 300), (2, 600)])
def test_explicit_rate_limit_keeps_long_backoff(fixed_now, attempt, seconds):
    error = AcquisitionFailed("failed", {"rate_limited": True})
    assert retry_delay(error, attempt, fixed_now) == (seconds, True)


@pytest.mark.parametrize(
    "header,seconds", [("42", 42), ("bad", 300), ("NaN", 300), ("999999", 300)]
)
def test_retry_after_is_bounded_and_invalid_values_fall_back(fixed_now, header, seconds):
    response = httpx.Response(
        429,
        headers={"Retry-After": header},
        request=httpx.Request("GET", "https://fixture.invalid"),
    )
    error = httpx.HTTPStatusError("limited", request=response.request, response=response)
    assert retry_delay(error, 1, fixed_now) == (seconds, True)


def test_wrapped_rate_limit_preserves_http_date_hint(fixed_now):
    header = format_datetime(fixed_now + timedelta(seconds=60))
    assert retry_delay(
        AcquisitionFailed("failed", {"rate_limited": True, "retry_after": header}), 1, fixed_now
    ) == (60, True)
