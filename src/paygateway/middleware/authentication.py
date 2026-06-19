import hashlib
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from paygateway.config import get_settings
from paygateway.db.session import get_db
from paygateway.models.api_key import ApiKey

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class AuthenticatedUser:
    def __init__(self, user_id: str, role: str, auth_type: str):
        self.user_id = user_id
        self.role = role
        self.auth_type = auth_type


def _hash_api_key(key: str) -> str:
    salted = f"{get_settings().API_KEY_SALT}{key}"
    return hashlib.sha256(salted.encode()).hexdigest()


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> AuthenticatedUser:
    if api_key:
        return await _authenticate_api_key(db, api_key)

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return _authenticate_jwt(token)

    raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "Missing authentication", "details": {}}})


async def _authenticate_api_key(db: AsyncSession, key: str) -> AuthenticatedUser:
    prefix = key[:8]
    stmt = select(ApiKey).where(ApiKey.key_prefix == prefix, ApiKey.is_active.is_(True))
    try:
        result = await db.execute(stmt)
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).error("DB auth error: %s: %s", type(_exc).__name__, _exc)
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "SERVICE_UNAVAILABLE", "message": "Database unavailable", "details": {}}},
        )
    api_key_record = result.scalar_one_or_none()

    if api_key_record is None:
        raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid API key", "details": {}}})

    key_hash = _hash_api_key(key)
    if api_key_record.key_hash != key_hash:
        raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid API key", "details": {}}})

    if api_key_record.expires_at and api_key_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "API key expired", "details": {}}})

    api_key_record.last_used_at = datetime.now(timezone.utc)

    return AuthenticatedUser(
        user_id=str(api_key_record.id),
        role=api_key_record.role,
        auth_type="api_key",
    )


def _authenticate_jwt(token: str) -> AuthenticatedUser:
    try:
        payload = jwt.decode(
            token,
            get_settings().JWT_SECRET_KEY,
            algorithms=[get_settings().JWT_ALGORITHM],
        )
    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid token", "details": {}}},
        ) from e

    user_id = payload.get("sub")
    role = payload.get("role", "readonly")
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid token payload", "details": {}}})

    return AuthenticatedUser(user_id=user_id, role=role, auth_type="jwt")


def require_role(*roles: str):
    async def _check(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "FORBIDDEN", "message": "Insufficient permissions", "details": {}}},
            )
        return user
    return _check
