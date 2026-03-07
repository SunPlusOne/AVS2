from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import asyncio

from api.schemas.contracts import TaskProgress
from api.services.ws_manager import WSManager
from api.utils.logger import log_json


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TaskRuntime:
    task_id: str
    file_id: str
    algorithm: str
    status: str
    progress: int
    current_frame: Optional[int]
    total_frames: Optional[int]
    message: Optional[str]
    created_at: datetime
    updated_at: datetime
    cancel_event: asyncio.Event
    handle: Optional[asyncio.Task]


class TaskManager:
    def __init__(self, tasks_dir: Path, ws: WSManager, logger) -> None:
        self._tasks_dir = tasks_dir
        self._ws = ws
        self._logger = logger
        self._tasks: dict[str, TaskRuntime] = {}
        self._lock = asyncio.Lock()

    def _task_path(self, task_id: str) -> Path:
        return self._tasks_dir / task_id / "task.json"

    async def create(self, file_id: str, algorithm: str) -> str:
        task_id = uuid.uuid4().hex
        rt = TaskRuntime(
            task_id=task_id,
            file_id=file_id,
            algorithm=algorithm,
            status="queued",
            progress=0,
            current_frame=None,
            total_frames=None,
            message=None,
            created_at=_now(),
            updated_at=_now(),
            cancel_event=asyncio.Event(),
            handle=None,
        )
        async with self._lock:
            self._tasks[task_id] = rt
        await self._persist(rt)
        await self._emit(rt)
        log_json(self._logger, "INFO", "task_created", {"task_id": task_id, "algorithm": algorithm})
        return task_id

    async def attach_handle(self, task_id: str, handle: asyncio.Task) -> None:
        async with self._lock:
            rt = self._tasks.get(task_id)
            if not rt:
                return
            rt.handle = handle

    async def get(self, task_id: str) -> TaskProgress:
        async with self._lock:
            rt = self._tasks.get(task_id)
        if rt:
            return TaskProgress(
                task_id=rt.task_id,
                status=rt.status,  # type: ignore
                progress=rt.progress,
                current_frame=rt.current_frame,
                total_frames=rt.total_frames,
                message=rt.message,
                algorithm=rt.algorithm,  # type: ignore
                created_at=rt.created_at,
                updated_at=rt.updated_at,
            )

        p = self._task_path(task_id)
        if not p.exists():
            raise KeyError(task_id)
        data = json.loads(p.read_text(encoding="utf-8"))
        persisted = TaskProgress(**data)

        # If backend restarted, in-memory runtime is gone and persisted running tasks
        # would otherwise stay "running" forever. Mark them as failed with a clear hint.
        if persisted.status in {"queued", "running"}:
            persisted.status = "failed"
            persisted.message = "任务在服务重启后中断，请重新提交。"
            persisted.updated_at = _now()
            p.write_text(
                json.dumps(persisted.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return persisted

    async def update(
        self,
        task_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        current_frame: Optional[int] = None,
        total_frames: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        async with self._lock:
            rt = self._tasks.get(task_id)
            if not rt:
                return
            if status is not None:
                rt.status = status
            if progress is not None:
                rt.progress = int(progress)
            if current_frame is not None:
                rt.current_frame = int(current_frame)
            if total_frames is not None:
                rt.total_frames = int(total_frames)
            if message is not None:
                rt.message = message
            rt.updated_at = _now()
        await self._persist(rt)
        await self._emit(rt)

    async def cancel(self, task_id: str) -> None:
        async with self._lock:
            rt = self._tasks.get(task_id)
            if not rt:
                return
            rt.cancel_event.set()
            if rt.handle and not rt.handle.done():
                rt.handle.cancel()
        await self.update(task_id, status="canceled", message="任务已取消")
        log_json(self._logger, "INFO", "task_canceled", {"task_id": task_id})

    async def cleanup(self, task_id: str) -> None:
        path = self._tasks_dir / task_id
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

        async with self._lock:
            self._tasks.pop(task_id, None)

    async def _persist(self, rt: TaskRuntime) -> None:
        p = self._task_path(rt.task_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = TaskProgress(
            task_id=rt.task_id,
            status=rt.status,  # type: ignore
            progress=rt.progress,
            current_frame=rt.current_frame,
            total_frames=rt.total_frames,
            message=rt.message,
            algorithm=rt.algorithm,  # type: ignore
            created_at=rt.created_at,
            updated_at=rt.updated_at,
        ).model_dump(mode="json")
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _emit(self, rt: TaskRuntime) -> None:
        payload: dict[str, Any] = TaskProgress(
            task_id=rt.task_id,
            status=rt.status,  # type: ignore
            progress=rt.progress,
            current_frame=rt.current_frame,
            total_frames=rt.total_frames,
            message=rt.message,
            algorithm=rt.algorithm,  # type: ignore
            created_at=rt.created_at,
            updated_at=rt.updated_at,
        ).model_dump(mode="json")
        await self._ws.broadcast(rt.task_id, payload)

