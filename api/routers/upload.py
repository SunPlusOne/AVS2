from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import get_settings
from api.config import Settings
from api.schemas.contracts import UploadResponse


router = APIRouter()


ALLOWED_EXT = {"mp4", "avi", "mov", "mkv"}


def _ext(name: str) -> str:
    parts = name.rsplit(".", 1)
    return parts[-1].lower() if len(parts) == 2 else ""


@router.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...), settings: Settings = Depends(get_settings)):
    ext = _ext(file.filename or "")
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="unsupported file type")

    file_id = uuid.uuid4().hex
    filename = file.filename or f"video.{ext}"
    save_path = settings.uploads_dir / f"{file_id}__{filename}"
    size = 0
    with save_path.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            size += len(chunk)

    return UploadResponse(file_id=file_id, filename=filename, size_bytes=size)
