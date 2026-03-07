from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.deps import get_settings, get_task_manager, get_task_runner
from api.config import Settings
from api.schemas.contracts import CreateTaskRequest, CreateTaskResponse, TaskProgress
from api.services.task_manager import TaskManager
from api.services.task_runner import TaskRunner


router = APIRouter()


_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@router.post("/tasks", response_model=CreateTaskResponse)
async def create_task(
    body: CreateTaskRequest,
    manager: TaskManager = Depends(get_task_manager),
    runner: TaskRunner = Depends(get_task_runner),
):
    task_id = await manager.create(file_id=body.file_id, algorithm=body.algorithm)
    handle = asyncio.create_task(runner.run(task_id=task_id, file_id=body.file_id, algorithm=body.algorithm))
    await manager.attach_handle(task_id, handle)
    return CreateTaskResponse(task_id=task_id)


@router.get("/tasks/{task_id}", response_model=TaskProgress)
async def get_task(task_id: str, manager: TaskManager = Depends(get_task_manager)):
    try:
        return await manager.get(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")


@router.delete("/tasks/{task_id}")
async def cancel_task(task_id: str, manager: TaskManager = Depends(get_task_manager)):
    await manager.cancel(task_id)
    return {"ok": True}


@router.get("/tasks/{task_id}/result")
async def download_result(task_id: str, settings: Settings = Depends(get_settings)):
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
async def download_masks(task_id: str, settings: Settings = Depends(get_settings)):
    path = settings.masks_dir / f"{task_id}.zip"
    if not path.exists():
        raise HTTPException(status_code=404, detail="masks not found")
    return FileResponse(
        str(path),
        media_type="application/zip",
        filename=f"{task_id}.zip",
        headers=_NO_CACHE_HEADERS,
    )
