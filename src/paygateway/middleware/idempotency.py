from fastapi import HTTPException, Request


def get_idempotency_key(request: Request) -> str:
    key = request.headers.get("Idempotency-Key")
    if not key:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "IDEMPOTENCY_KEY_MISSING",
                    "message": "Idempotency-Key header is required for this request",
                    "details": {},
                }
            },
        )
    if len(key) > 255:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "IDEMPOTENCY_KEY_INVALID",
                    "message": "Idempotency-Key must be 255 characters or fewer",
                    "details": {},
                }
            },
        )
    return key
