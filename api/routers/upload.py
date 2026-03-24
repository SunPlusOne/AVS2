from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import get_settings
from api.config import Settings
from api.schemas.contracts import UploadResponse
from api.services.auth import user_guard
from api.services.media_inspector import probe_video_metadata


router = APIRouter()


ALLOWED_EXT = {"mp4", "avi", "mov", "mkv"}


def _ext(name: str) -> str:
    parts = name.rsplit(".", 1)
    return parts[-1].lower() if len(parts) == 2 else ""


@router.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...), settings: Settings = Depends(get_settings), ok=Depends(user_guard)):
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

    meta = probe_video_metadata(save_path)

    sidecar = settings.uploads_dir / f"{file_id}.meta.json"
    sidecar.write_text(
        json.dumps(
            {
                "file_id": file_id,
                "filename": filename,
                "size_bytes": size,
                "duration_seconds": meta.duration_seconds,
                "width": meta.width,
                "height": meta.height,
                "fps": meta.fps,
                "total_frames": meta.total_frames,
                "audio_energy": meta.audio_energy,
                "recommended_scene": meta.recommended_scene,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return UploadResponse(
        file_id=file_id,
        filename=filename,
        size_bytes=size,
        duration_seconds=meta.duration_seconds,
        width=meta.width,
        height=meta.height,
        fps=meta.fps,
        total_frames=meta.total_frames,
        audio_energy=meta.audio_energy,
        recommended_scene=meta.recommended_scene,  # type: ignore[arg-type]
    )
