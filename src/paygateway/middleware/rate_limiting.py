import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from paygateway.config import get_settings


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_rate_limited(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, dict]:
        now = time.time()
        window_start = now - window_seconds

        self._requests[key] = [t for t in self._requests[key] if t > window_start]
        self._requests[key].append(now)

        remaining = max(0, limit - len(self._requests[key]))
        reset_at = int(now + window_seconds)

        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }

        if len(self._requests[key]) > limit:
            headers["Retry-After"] = str(window_seconds)
            return True, headers

        return False, headers


_limiter = InMemoryRateLimiter()

RATE_LIMITS: dict[str, int] = {
    "/api/v1/payments": 30,
    "/api/v1/refunds": 10,
    "/api/v1/admin/reconciliation": 5,
    "/api/v1/webhooks": 300,
    "/health": 60,
    "/info": 60,
}


def _get_limit_for_path(path: str) -> int:
    for prefix, limit in RATE_LIMITS.items():
        if path.startswith(prefix):
            return limit
    return 120


def _get_rate_key(request: Request) -> str:
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        return f"apikey:{api_key[:8]}"
    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not get_settings().RATE_LIMIT_ENABLED:
            return await call_next(request)

        key = _get_rate_key(request)
        limit = _get_limit_for_path(request.url.path)
        is_limited, headers = _limiter.is_rate_limited(key, limit)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={"detail": {"error": {"code": "RATE_LIMITED", "message": "Rate limit exceeded", "details": {}}}},
                headers=headers,
            )

        response = await call_next(request)
        for k, v in headers.items():
            response.headers[k] = v
        return response
