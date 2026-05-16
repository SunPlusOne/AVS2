from __future__ import annotations

import asyncio
import json
import zipfile
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response

from api.deps import (
    get_fusion_service,
    get_logs_repo,
    get_settings,
    get_task_manager,
    get_task_runner,
    get_tasks_repo,
    get_users_repo,
)
from api.config import Settings
from api.schemas.contracts import CreateTaskRequest, CreateTaskResponse, TaskProgress
from api.services.auth import user_guard, user_guard_with_query_token
from api.services.fusion_service import FusionService
from api.services.logs_repo import LogsRepo
from api.services.task_manager import TaskManager
from api.services.tasks_repo import TasksRepo
from api.services.task_runner import TaskRunner
from api.services.users_repo import UsersRepo


router = APIRouter()


_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


async def _to_thread_compat(fn, /, *args, **kwargs):
    if hasattr(asyncio, "to_thread"):
        return await asyncio.to_thread(fn, *args, **kwargs)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


def _ensure_task_access(task_id: str, ok: dict, tasks_repo: TasksRepo) -> None:
    role = str(ok.get("role", ""))
    if role == "admin":
        if not tasks_repo.exists(task_uid=task_id):
            raise HTTPException(status_code=404, detail="task not found")
        return

    username = str(ok.get("username", ""))
    owner = tasks_repo.get_owner_username(task_uid=task_id)
    if owner is None:
        if tasks_repo.exists(task_uid=task_id):
            raise HTTPException(status_code=403, detail="forbidden")
        raise HTTPException(status_code=404, detail="task not found")
    if owner != username:
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("/tasks", response_model=List[TaskProgress])
async def list_tasks(
    username: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    manager: TaskManager = Depends(get_task_manager),
    tasks_repo: TasksRepo = Depends(get_tasks_repo),
    ok=Depends(user_guard),
):
    role = str(ok.get("role", ""))
    requester = str(ok.get("username", ""))
    effective_username: Optional[str] = None

    if role == "admin":
        effective_username = username.strip() if username else None
    else:
        if username and username.strip() and username.strip() != requester:
            raise HTTPException(status_code=403, detail="forbidden")
        effective_username = requester

    rows = tasks_repo.list_task_rows(username=effective_username, limit=limit)
    items: list[TaskProgress] = []
    for row in rows:
        task_uid = str(row.get("task_uid", ""))
        if not task_uid:
            continue
        try:
            task = await manager.get(task_uid)
        except KeyError:
            continue
        task.owner_username = row.get("username")
        items.append(task)
    return items


@router.post("/tasks", response_model=CreateTaskResponse)
async def create_task(
    body: CreateTaskRequest,
    manager: TaskManager = Depends(get_task_manager),
    runner: TaskRunner = Depends(get_task_runner),
    users_repo: UsersRepo = Depends(get_users_repo),
    logs_repo: LogsRepo = Depends(get_logs_repo),
    ok=Depends(user_guard),
):
    username = str(ok.get("username", ""))
    task_id = await manager.create(
        file_id=body.file_id,
        algorithm=body.algorithm,
        scene=body.scene,
        username=username,
    )
    profile = users_repo.get_by_username(username)
    logs_repo.add(
        user_id=int(profile["id"]) if profile and profile.get("id") else None,
        action=f"提交任务 {task_id} ({body.algorithm})",
        ip=None,
    )
    handle = asyncio.create_task(
        runner.run(task_id=task_id, file_id=body.file_id, algorithm=body.algorithm, scene=body.scene)
    )
    await manager.attach_handle(task_id, handle)
    return CreateTaskResponse(task_id=task_id)


@router.get("/tasks/{task_id}", response_model=TaskProgress)
async def get_task(
    task_id: str,
    manager: TaskManager = Depends(get_task_manager),
    tasks_repo: TasksRepo = Depends(get_tasks_repo),
    ok=Depends(user_guard),
):
    _ensure_task_access(task_id, ok, tasks_repo)
    try:
        task = await manager.get(task_id)
        task.owner_username = tasks_repo.get_owner_username(task_uid=task_id)
        return task
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")


@router.delete("/tasks/{task_id}")
async def cancel_task(
    task_id: str,
    manager: TaskManager = Depends(get_task_manager),
    tasks_repo: TasksRepo = Depends(get_tasks_repo),
    ok=Depends(user_guard),
):
    _ensure_task_access(task_id, ok, tasks_repo)
    await manager.cancel(task_id)
    return {"ok": True}


@router.get("/tasks/{task_id}/result")
async def download_result(
    task_id: str,
    settings: Settings = Depends(get_settings),
    tasks_repo: TasksRepo = Depends(get_tasks_repo),
    ok=Depends(user_guard_with_query_token),
):
    _ensure_task_access(task_id, ok, tasks_repo)
    path = settings.results_dir / f"{task_id}.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="result not found")
    return FileResponse(
        str(path),
        media_type="video/mp4",
        filename=f"{task_id}.mp4",
        headers=_NO_CACHE_HEADERS,
    )


@router.get("/tasks/{task_id}/masks")
async def download_masks(
    task_id: str,
    settings: Settings = Depends(get_settings),
    tasks_repo: TasksRepo = Depends(get_tasks_repo),
    ok=Depends(user_guard_with_query_token),
):
    _ensure_task_access(task_id, ok, tasks_repo)
    path = settings.masks_dir / f"{task_id}.zip"
    if not path.exists():
        raise HTTPException(status_code=404, detail="masks not found")
    return FileResponse(
        str(path),
        media_type="application/zip",
        filename=f"{task_id}.zip",
        headers=_NO_CACHE_HEADERS,
    )


@router.get("/tasks/{task_id}/mask/{frame_no}")
async def download_mask_frame(
    task_id: str,
    frame_no: int,
    settings: Settings = Depends(get_settings),
    tasks_repo: TasksRepo = Depends(get_tasks_repo),
    ok=Depends(user_guard_with_query_token),
):
    _ensure_task_access(task_id, ok, tasks_repo)
    if frame_no <= 0:
        raise HTTPException(status_code=400, detail="invalid frame number")

    path = settings.masks_dir / f"{task_id}.zip"
    if not path.exists():
        raise HTTPException(status_code=404, detail="masks not found")

    target_name = f"mask_{frame_no:04d}.png"
    alternatives = [target_name, f"{frame_no:04d}.png", f"{frame_no}.png"]
    mask_bytes: bytes | None = None

    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            for name in alternatives:
                if name in names:
                    mask_bytes = zf.read(name)
                    break

            if mask_bytes is None:
                for name in names:
                    lower = name.lower()
                    if not lower.endswith(".png"):
                        continue
                    base = lower.rsplit("/", 1)[-1]
                    if base == target_name:
                        mask_bytes = zf.read(name)
                        break
    except zipfile.BadZipFile:
        raise HTTPException(status_code=500, detail="masks archive is corrupted")
    except KeyError:
        raise HTTPException(status_code=404, detail="mask frame not found")

    if mask_bytes is None:
        raise HTTPException(status_code=404, detail="mask frame not found")

    headers = {**_NO_CACHE_HEADERS, "Content-Type": "image/png"}
    return Response(content=mask_bytes, media_type="image/png", headers=headers)


@router.get("/tasks/{task_id}/report")
async def get_task_report(
    task_id: str,
    settings: Settings = Depends(get_settings),
    tasks_repo: TasksRepo = Depends(get_tasks_repo),
    ok=Depends(user_guard),
):
    _ensure_task_access(task_id, ok, tasks_repo)
    path = settings.results_dir / f"{task_id}.report.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="report not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="report parse failed")
    return data


@router.get("/fusions/intersection/result")
async def download_intersection_fusion_result(
    task_id: List[str] = Query(default=[]),
    tasks_repo: TasksRepo = Depends(get_tasks_repo),
    fusion_service: FusionService = Depends(get_fusion_service),
    ok=Depends(user_guard_with_query_token),
):
    ids = [str(x).strip() for x in task_id if str(x).strip()]
    # Keep user-selected ordering while removing duplicates.
    ids = list(dict.fromkeys(ids))
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="at least two task_id are required")

    for one_id in ids:
        _ensure_task_access(one_id, ok, tasks_repo)

    try:
        out_path = await _to_thread_compat(
            fusion_service.get_or_build_intersection_video,
            task_ids=ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not out_path.exists():
        raise HTTPException(status_code=404, detail="fusion result not found")

    return FileResponse(
        str(out_path),
        media_type="video/mp4",
        filename=out_path.name,
        headers=_NO_CACHE_HEADERS,
    )
