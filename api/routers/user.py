from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.config import Settings
from api.deps import get_settings, get_users_repo
from api.schemas.contracts import UserLoginRequest, UserLoginResponse, UserRegisterRequest
from api.services.auth import issue_jwt
from api.services.users_repo import UsersRepo


router = APIRouter()


@router.post("/user/register")
async def user_register(body: UserRegisterRequest, repo: UsersRepo = Depends(get_users_repo)):
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="username required")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="password too short")

    try:
        repo.create_user(username, body.password)
    except ValueError as e:
        msg = str(e)
        if msg == "username exists":
            raise HTTPException(status_code=409, detail="username exists")
        raise HTTPException(status_code=400, detail=msg)

    return {"ok": True}


@router.post("/user/login", response_model=UserLoginResponse)
async def user_login(
    body: UserLoginRequest,
    settings: Settings = Depends(get_settings),
    repo: UsersRepo = Depends(get_users_repo),
):
    profile = repo.verify_user(body.username, body.password)
    if not profile:
        raise HTTPException(status_code=401, detail="invalid credentials")

    token, expires_at = issue_jwt(settings, profile["username"], "user")
    return UserLoginResponse(token=token, expires_at=expires_at, role="user")
