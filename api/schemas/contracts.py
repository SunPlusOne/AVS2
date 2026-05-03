from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


AlgorithmId = Literal["avsegformer", "avis", "vct", "combo"]
SceneId = Literal["single_source", "multi_source", "auto_detect"]
TaskStatus = Literal["queued", "running", "completed", "failed", "canceled"]


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    size_bytes: int
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    total_frames: Optional[int] = None
    audio_energy: Optional[float] = None
    recommended_scene: Optional[Literal["single_source", "multi_source"]] = None


class TaskMetrics(BaseModel):
    jaccard: Optional[float] = None
    f_measure: Optional[float] = None
    jf_mean: Optional[float] = None
    total_inference_ms: Optional[int] = None
    avg_frame_ms: Optional[float] = None
    processed_frames: Optional[int] = None


class CreateTaskRequest(BaseModel):
    file_id: str
    algorithm: AlgorithmId
    scene: Optional[SceneId] = None


class CreateTaskResponse(BaseModel):
    task_id: str


class TaskProgress(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int = Field(ge=0, le=100)
    current_frame: Optional[int] = None
    total_frames: Optional[int] = None
    message: Optional[str] = None
    algorithm: Optional[AlgorithmId] = None
    scene: Optional[SceneId] = None
    resolved_scene: Optional[Literal["single_source", "multi_source"]] = None
    filename: Optional[str] = None
    fps: Optional[float] = None
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    metrics: Optional[TaskMetrics] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AlgorithmInfo(BaseModel):
    id: str
    name: str
    version: Optional[str] = None
    description: str
    input_size: Optional[str] = None
    enabled: bool


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    token: str
    expires_at: str
    role: Literal["admin", "user"]


class UserRegisterRequest(BaseModel):
    username: str
    password: str


class UserLoginRequest(BaseModel):
    username: str
    password: str


class UserLoginResponse(BaseModel):
    token: str
    expires_at: str
    role: Literal["admin", "user"]


class LogEntry(BaseModel):
    ts: str
    level: str
    message: str

