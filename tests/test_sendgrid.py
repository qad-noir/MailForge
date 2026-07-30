from datetime import UTC, datetime

import pytest

from app.integrations.sendgrid.client import classify_retryable, parse_retry_after
from app.workers.sender import calculate_backoff


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retryable_statuses(status: int) -> None:
    assert classify_retryable(status)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_permanent_statuses(status: int) -> None:
    assert not classify_retryable(status)


def test_retry_after_seconds_and_http_date() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert parse_retry_after("12", now) == 12
    assert parse_retry_after("Thu, 01 Jan 2026 00:00:30 GMT", now) == 30


def test_backoff_is_exponential_with_bounded_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.workers.sender.random.uniform", lambda _a, _b: 1.0)
    assert calculate_backoff(1) == 2
    assert calculate_backoff(4) == 16
    assert calculate_backoff(20) == 3600
