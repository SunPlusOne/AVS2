from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from api.config import Settings
from api.deps import get_settings


security = HTTPBearer(auto_error=False)


def issue_admin_jwt(settings: Settings) -> tuple[str, str]:
    exp = datetime.now(timezone.utc) + timedelta(hours=24)
    payload: dict[str, Any] = {
        "sub": "admin",
        "iss": settings.admin_jwt_issuer,
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, settings.admin_jwt_secret, algorithm="HS256")
    return token, exp.isoformat()


def require_admin(settings: Settings):
    async def _dep(creds: HTTPAuthorizationCredentials | None = Depends(security)):
        if not creds or creds.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="missing token")
        token = creds.credentials
        try:
            data = jwt.decode(token, settings.admin_jwt_secret, algorithms=["HS256"], issuer=settings.admin_jwt_issuer)
        except JWTError:
            raise HTTPException(status_code=401, detail="invalid token")
        if data.get("sub") != "admin":
            raise HTTPException(status_code=403, detail="forbidden")
        return True

    return _dep


async def admin_guard(
    settings: Settings = Depends(get_settings),
    creds: HTTPAuthorizationCredentials | None = Depends(security),
):
    dep = require_admin(settings)
    return await dep(creds)
