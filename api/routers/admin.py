from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from api.config import Settings
from api.deps import get_logs_repo, get_settings, get_users_repo
from api.schemas.contracts import AdminLoginRequest, AdminLoginResponse, LogEntry
from api.services.logs_repo import LogsRepo
from api.services.auth import admin_guard, issue_jwt
from api.services.users_repo import UsersRepo


router = APIRouter()


@router.post("/admin/login", response_model=AdminLoginResponse)
async def admin_login(
    body: AdminLoginRequest,
    settings: Settings = Depends(get_settings),
    users_repo: UsersRepo = Depends(get_users_repo),
):
    profile = users_repo.verify_user(body.username, body.password, role="admin")
    if not profile:
        raise HTTPException(status_code=401, detail="invalid password")
    token, expires_at = issue_jwt(settings, profile["username"], "admin")
    return AdminLoginResponse(token=token, expires_at=expires_at, role="admin")


@router.get("/admin/logs", response_model=List[LogEntry])
async def get_logs(
    repo: LogsRepo = Depends(get_logs_repo),
    ok=Depends(admin_guard),
    limit: int = 200,
):
    rows = repo.list_latest(limit=limit)
    return [LogEntry(ts=r["ts"], level=r["level"], message=r["message"]) for r in rows]
