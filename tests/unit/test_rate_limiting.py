from unittest.mock import MagicMock

import pytest

from paygateway.middleware.rate_limiting import (
    InMemoryRateLimiter,
    _get_limit_for_path,
    _get_rate_key,
)


def _make_request(api_key: str | None = None, ip: str = "1.2.3.4") -> MagicMock:
    req = MagicMock()
    req.headers = {"X-API-Key": api_key} if api_key else {}
    req.client = MagicMock()
    req.client.host = ip
    return req


# ---------------------------------------------------------------------------
# InMemoryRateLimiter
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_first_request_is_allowed():
    limiter = InMemoryRateLimiter()
    limited, headers = limiter.is_rate_limited("key-1", limit=10)
    assert limited is False


@pytest.mark.unit
def test_response_headers_always_present():
    limiter = InMemoryRateLimiter()
    _, headers = limiter.is_rate_limited("key-h", limit=10)
    assert "X-RateLimit-Limit" in headers
    assert "X-RateLimit-Remaining" in headers
    assert "X-RateLimit-Reset" in headers
    assert headers["X-RateLimit-Limit"] == "10"


@pytest.mark.unit
def test_remaining_decrements_per_request():
    limiter = InMemoryRateLimiter()
    for _ in range(5):
        _, headers = limiter.is_rate_limited("key-dec", limit=10)
    assert headers["X-RateLimit-Remaining"] == "5"


@pytest.mark.unit
def test_exceeding_limit_returns_429():
    limiter = InMemoryRateLimiter()
    for _ in range(5):
        limiter.is_rate_limited("key-over", limit=5)
    limited, headers = limiter.is_rate_limited("key-over", limit=5)
    assert limited is True
    assert "Retry-After" in headers


@pytest.mark.unit
def test_different_keys_are_isolated():
    limiter = InMemoryRateLimiter()
    for _ in range(5):
        limiter.is_rate_limited("key-a", limit=5)
    # key-a is now at the limit; key-b should still be allowed
    limited, _ = limiter.is_rate_limited("key-b", limit=5)
    assert limited is False


# ---------------------------------------------------------------------------
# _get_rate_key
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rate_key_uses_api_key_prefix_when_present():
    req = _make_request(api_key="pgw_test_abc123fullkey")
    key = _get_rate_key(req)
    assert key == "apikey:pgw_test"


@pytest.mark.unit
def test_rate_key_falls_back_to_client_ip():
    req = _make_request(api_key=None, ip="10.0.0.1")
    key = _get_rate_key(req)
    assert key == "ip:10.0.0.1"


@pytest.mark.unit
def test_rate_key_uses_unknown_when_no_client():
    req = _make_request(api_key=None)
    req.client = None
    key = _get_rate_key(req)
    assert key == "ip:unknown"


# ---------------------------------------------------------------------------
# _get_limit_for_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_payments_path_limit():
    assert _get_limit_for_path("/api/v1/payments") == 30


@pytest.mark.unit
def test_payments_sub_path_inherits_limit():
    assert _get_limit_for_path("/api/v1/payments/some-id/confirm") == 30


@pytest.mark.unit
def test_webhooks_path_limit():
    assert _get_limit_for_path("/api/v1/webhooks/stripe") == 300


@pytest.mark.unit
def test_health_path_limit():
    assert _get_limit_for_path("/health") == 60


@pytest.mark.unit
def test_unknown_path_returns_default():
    assert _get_limit_for_path("/unknown/route") == 120
