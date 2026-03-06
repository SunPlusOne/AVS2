from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.config import Settings
from api.deps import get_algorithms_repo, get_settings
from api.schemas.contracts import AdminLoginRequest, AdminLoginResponse, LogEntry
from api.services.algorithms_repo import AlgorithmsRepo
from api.services.auth import admin_guard, issue_admin_jwt


router = APIRouter()


@router.post("/admin/login", response_model=AdminLoginResponse)
async def admin_login(body: AdminLoginRequest, settings: Settings = Depends(get_settings)):
    if body.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="invalid password")
    token, expires_at = issue_admin_jwt(settings)
    return AdminLoginResponse(token=token, expires_at=expires_at)


@router.post("/admin/models")
async def upload_model(
    settings: Settings = Depends(get_settings),
    repo: AlgorithmsRepo = Depends(get_algorithms_repo),
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

    repo.upsert(
        {
            "id": algorithm_id,
            "name": name,
            "version": version,
            "description": description,
            "input_size": input_size,
            "enabled": enabled.lower() == "true",
            "weight_path": str(save_path),
        }
    )

    return {"ok": True}


@router.get("/admin/logs", response_model=List[LogEntry])
async def get_logs(
    settings: Settings = Depends(get_settings),
    ok=Depends(admin_guard),
    limit: int = 200,
):
    limit = max(1, min(limit, 1000))
    log_path = settings.logs_dir / "app.log"
    if not log_path.exists():
        return []

    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
    out: List[LogEntry] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                out.append(LogEntry(ts=str(obj.get("ts", "")), level=str(obj.get("level", "INFO")), message=str(obj.get("message", ""))))
        except Exception:
            continue
    return out
