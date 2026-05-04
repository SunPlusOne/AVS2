from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request

from api.config import Settings
from api.deps import get_logs_repo, get_settings, get_users_repo
from api.schemas.contracts import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminUserProfile,
    LogEntry,
    UpdateUserRoleRequest,
    UpdateUserRoleResponse,
)
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


@router.get("/admin/users", response_model=List[AdminUserProfile])
async def list_users(
    users_repo: UsersRepo = Depends(get_users_repo),
    ok=Depends(admin_guard),
):
    rows = users_repo.list_users()
    return [
        AdminUserProfile(
            id=int(r["id"]),
            username=str(r["username"]),
            role=str(r["role"]),
            created_at=r["created_at"],
            last_login=r.get("last_login"),
        )
        for r in rows
    ]


@router.patch("/admin/users/{user_id}/role", response_model=UpdateUserRoleResponse)
async def update_user_role(
    user_id: int,
    body: UpdateUserRoleRequest,
    request: Request,
    users_repo: UsersRepo = Depends(get_users_repo),
    logs_repo: LogsRepo = Depends(get_logs_repo),
    actor=Depends(admin_guard),
):
    if user_id <= 0:
        raise HTTPException(status_code=400, detail="invalid user id")

    updated = users_repo.update_user_role(user_id, body.role)
    if not updated:
        raise HTTPException(status_code=404, detail="user not found")

    actor_name = str(actor.get("username", "admin")) if isinstance(actor, dict) else "admin"
    logs_repo.add(
        user_id=None,
        action=f"管理员 {actor_name} 修改用户 {updated['username']} 角色为 {updated['role']}",
        ip=request.client.host if request.client else None,
    )

    profile = AdminUserProfile(
        id=int(updated["id"]),
        username=str(updated["username"]),
        role=str(updated["role"]),
        created_at=updated["created_at"],
        last_login=updated.get("last_login"),
    )
    return UpdateUserRoleResponse(ok=True, user=profile)
