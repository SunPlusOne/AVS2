from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


AlgorithmId = Literal["avsegformer", "vct", "combo"]
TaskStatus = Literal["queued", "running", "completed", "failed", "canceled"]


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    size_bytes: int


class CreateTaskRequest(BaseModel):
    file_id: str
    algorithm: AlgorithmId


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
    password: str


class AdminLoginResponse(BaseModel):
    token: str
    expires_at: str


class LogEntry(BaseModel):
    ts: str
    level: str
    message: str

