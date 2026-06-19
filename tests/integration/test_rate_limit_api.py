"""
Integration tests for rate-limiting middleware.
RATE_LIMIT_ENABLED is False in test env (set in conftest).
Tests here use monkeypatch to enable it selectively.
"""
import pytest
from httpx import AsyncClient

import paygateway.middleware.rate_limiting as _rl


@pytest.mark.integration
async def test_rate_limit_headers_present_when_enabled(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """When rate limiting is on, every response carries X-RateLimit-* headers."""

    class _FakeSettings:
        RATE_LIMIT_ENABLED = True

    monkeypatch.setattr(_rl, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(_rl, "_limiter", _rl.InMemoryRateLimiter())

    resp = await client.get("/api/v1/payments")

    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers
    assert "x-ratelimit-remaining" in resp.headers
    assert "x-ratelimit-reset" in resp.headers


@pytest.mark.integration
async def test_rate_limit_returns_429_when_exceeded(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """After N requests equal to the configured limit, the next one returns 429."""

    class _FakeSettings:
        RATE_LIMIT_ENABLED = True

    fresh_limiter = _rl.InMemoryRateLimiter()
    monkeypatch.setattr(_rl, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(_rl, "_limiter", fresh_limiter)
    # Drop the payments limit to 2 so we don't need 30 requests
    monkeypatch.setattr(_rl, "RATE_LIMITS", {"/api/v1/payments": 2})

    for _ in range(2):
        r = await client.get("/api/v1/payments")
        assert r.status_code == 200

    resp = await client.get("/api/v1/payments")
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"]["code"] == "RATE_LIMITED"
    assert "retry-after" in resp.headers
