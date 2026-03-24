from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from api.config import Settings
from api.deps import get_settings


security = HTTPBearer(auto_error=False)


def issue_jwt(settings: Settings, username: str, role: str) -> tuple[str, str]:
    exp = datetime.now(timezone.utc) + timedelta(hours=24)
    payload: dict[str, Any] = {
        "sub": username,
        "role": role,
        "iss": settings.admin_jwt_issuer,
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, settings.admin_jwt_secret, algorithm="HS256")
    return token, exp.isoformat()


def issue_admin_jwt(settings: Settings) -> tuple[str, str]:
    return issue_jwt(settings, settings.admin_username, "admin")


def require_roles(settings: Settings, allowed_roles: set[str]):
    # Use Optional or Union[..., None] for compatibility with Python 3.8
    async def _dep(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)):
        if not creds or creds.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="missing token")
        token = creds.credentials
        try:
            data = jwt.decode(token, settings.admin_jwt_secret, algorithms=["HS256"], issuer=settings.admin_jwt_issuer)
        except JWTError:
            raise HTTPException(status_code=401, detail="invalid token")
        role = data.get("role")
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail="forbidden")
        return {"username": str(data.get("sub", "")), "role": str(role)}

    return _dep


def require_admin(settings: Settings):
    return require_roles(settings, {"admin"})


async def admin_guard(
    settings: Settings = Depends(get_settings),
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    dep = require_admin(settings)
    return await dep(creds)


async def user_guard(
    settings: Settings = Depends(get_settings),
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    dep = require_roles(settings, {"admin", "user"})
    return await dep(creds)
