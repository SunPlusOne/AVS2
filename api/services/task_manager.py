from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import asyncio

from api.schemas.contracts import TaskMetrics, TaskProgress
from api.services.algorithms_repo import AlgorithmsRepo
from api.services.tasks_repo import TasksRepo
from api.services.users_repo import UsersRepo
from api.services.ws_manager import WSManager
from api.utils.logger import log_json


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TaskRuntime:
    task_id: str
    file_id: str
    algorithm: str
    scene: Optional[str]
    resolved_scene: Optional[str]
    filename: Optional[str]
    status: str
    progress: int
    current_frame: Optional[int]
    total_frames: Optional[int]
    fps: Optional[float]
    duration_seconds: Optional[float]
    width: Optional[int]
    height: Optional[int]
    metrics: Optional[TaskMetrics]
    message: Optional[str]
    created_at: datetime
    updated_at: datetime
    cancel_event: asyncio.Event
    handle: Optional[asyncio.Task]


class TaskManager:
    def __init__(
        self,
        tasks_dir: Path,
        uploads_dir: Path,
        ws: WSManager,
        logger,
        *,
        tasks_repo: TasksRepo,
        algorithms_repo: AlgorithmsRepo,
        users_repo: UsersRepo,
    ) -> None:
        self._tasks_dir = tasks_dir
        self._uploads_dir = uploads_dir
        self._ws = ws
        self._logger = logger
        self._tasks_repo = tasks_repo
        self._algorithms_repo = algorithms_repo
        self._users_repo = users_repo
        self._tasks: dict[str, TaskRuntime] = {}
        self._lock = asyncio.Lock()

    def _task_path(self, task_id: str) -> Path:
        return self._tasks_dir / task_id / "task.json"

    def _upload_meta_path(self, file_id: str) -> Path:
        return self._uploads_dir / f"{file_id}.meta.json"

    def _guess_filename(self, file_id: str) -> Optional[str]:
        matches = list(self._uploads_dir.glob(f"{file_id}__*"))
        if not matches:
            return None
        name = matches[0].name
        sep = "__"
        if sep in name:
            return name.split(sep, 1)[1]
        return matches[0].name

    def _load_upload_meta(self, file_id: str) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        p = self._upload_meta_path(file_id)
        if p.exists():
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
        if "filename" not in payload:
            payload["filename"] = self._guess_filename(file_id)
        return payload

    async def create(
        self,
        file_id: str,
        algorithm: str,
        scene: Optional[str] = None,
        username: Optional[str] = None,
    ) -> str:
        task_id = uuid.uuid4().hex
        upload_meta = self._load_upload_meta(file_id)
        resolved_scene = scene

        metrics_payload = upload_meta.get("metrics")
        parsed_metrics: Optional[TaskMetrics] = None
        if isinstance(metrics_payload, dict):
            try:
                parsed_metrics = TaskMetrics(**metrics_payload)
            except Exception:
                parsed_metrics = None

        rt = TaskRuntime(
            task_id=task_id,
            file_id=file_id,
            algorithm=algorithm,
            scene=scene,
            resolved_scene=resolved_scene,
            filename=upload_meta.get("filename"),
            status="queued",
            progress=0,
            current_frame=None,
            total_frames=upload_meta.get("total_frames"),
            fps=upload_meta.get("fps"),
            duration_seconds=upload_meta.get("duration_seconds"),
            width=upload_meta.get("width"),
            height=upload_meta.get("height"),
            metrics=parsed_metrics,
            message=None,
            created_at=_now(),
            updated_at=_now(),
            cancel_event=asyncio.Event(),
            handle=None,
        )
        async with self._lock:
            self._tasks[task_id] = rt

        user_id: Optional[int] = None
        if username:
            profile = self._users_repo.get_by_username(username)
            if profile and profile.get("id"):
                user_id = int(profile["id"])

        model_id = self._algorithms_repo.find_model_id(algorithm)
        input_path = str(self._uploads_dir / f"{file_id}__{upload_meta.get('filename')}") if upload_meta.get("filename") else None
        self._tasks_repo.create_task(
            task_uid=task_id,
            user_id=user_id,
            model_id=model_id,
            input_path=input_path,
        )

        await self._persist(rt)
        await self._emit(rt)
        log_json(
            self._logger,
            "INFO",
            "task_created",
            {"task_id": task_id, "algorithm": algorithm, "scene": scene},
        )
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
                scene=rt.scene,  # type: ignore
                resolved_scene=rt.resolved_scene,  # type: ignore
                filename=rt.filename,
                fps=rt.fps,
                duration_seconds=rt.duration_seconds,
                width=rt.width,
                height=rt.height,
                metrics=rt.metrics,
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
        resolved_scene: Optional[str] = None,
        fps: Optional[float] = None,
        duration_seconds: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        metrics: Optional[TaskMetrics] = None,
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
            if resolved_scene is not None:
                rt.resolved_scene = resolved_scene
            if fps is not None:
                rt.fps = float(fps)
            if duration_seconds is not None:
                rt.duration_seconds = float(duration_seconds)
            if width is not None:
                rt.width = int(width)
            if height is not None:
                rt.height = int(height)
            if metrics is not None:
                rt.metrics = metrics
            if message is not None:
                rt.message = message
            rt.updated_at = _now()

        if status is not None:
            output_path = None
            finished_at = None
            if status == "completed":
                output_path = str(self._tasks_dir.parent / "results" / f"{task_id}.mp4")
                finished_at = _now()
            elif status in {"failed", "canceled"}:
                finished_at = _now()
            self._tasks_repo.update_task_status(
                task_uid=task_id,
                status=status,
                output_path=output_path,
                finished_at=finished_at,
            )

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
            scene=rt.scene,  # type: ignore
            resolved_scene=rt.resolved_scene,  # type: ignore
            filename=rt.filename,
            fps=rt.fps,
            duration_seconds=rt.duration_seconds,
            width=rt.width,
            height=rt.height,
            metrics=rt.metrics,
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
            scene=rt.scene,  # type: ignore
            resolved_scene=rt.resolved_scene,  # type: ignore
            filename=rt.filename,
            fps=rt.fps,
            duration_seconds=rt.duration_seconds,
            width=rt.width,
            height=rt.height,
            metrics=rt.metrics,
            created_at=rt.created_at,
            updated_at=rt.updated_at,
        ).model_dump(mode="json")
        await self._ws.broadcast(rt.task_id, payload)

