from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from api.config import Settings
from api.deps import get_algorithms_repo, get_logs_repo, get_settings, get_users_repo
from api.schemas.contracts import AdminLoginRequest, AdminLoginResponse, LogEntry
from api.services.algorithms_repo import AlgorithmsRepo
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


@router.post("/admin/models")
async def upload_model(
    request: Request,
    settings: Settings = Depends(get_settings),
    repo: AlgorithmsRepo = Depends(get_algorithms_repo),
    users_repo: UsersRepo = Depends(get_users_repo),
    logs_repo: LogsRepo = Depends(get_logs_repo),
    ok=Depends(admin_guard),
    algorithm_id: str = Form(...),
    name: str = Form(...),
    version: str = Form(...),
    description: str = Form(...),
    input_size: str = Form(""),
    enabled: str = Form("true"),
    file: UploadFile = File(...),
):
    if not (file.filename or "").lower().endswith(".pth"):
        raise HTTPException(status_code=400, detail="only .pth is allowed")

    model_dir = settings.models_dir / algorithm_id / version
    model_dir.mkdir(parents=True, exist_ok=True)
    save_path = model_dir / (file.filename or "weights.pth")
    with save_path.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    actor = users_repo.get_by_username(str(ok.get("username", "")))
    actor_id = int(actor["id"]) if actor and actor.get("id") else None

    repo.upsert(
        {
            "id": algorithm_id,
            "name": name,
            "version": version,
            "description": description,
            "input_size": input_size,
            "enabled": enabled.lower() == "true",
            "weight_path": str(save_path),
        },
        uploaded_by=actor_id,
    )

    logs_repo.add(
        user_id=actor_id,
        action=f"上传模型 {name}-{version}",
        ip=request.client.host if request.client else None,
    )

    return {"ok": True}


@router.get("/admin/logs", response_model=List[LogEntry])
async def get_logs(
    repo: LogsRepo = Depends(get_logs_repo),
    ok=Depends(admin_guard),
    limit: int = 200,
):
    rows = repo.list_latest(limit=limit)
    return [LogEntry(ts=r["ts"], level=r["level"], message=r["message"]) for r in rows]
